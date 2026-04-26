from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ImprProductionProcess(models.Model):
    _name = 'impr.production.process'
    _description = 'Proceso de producción (Gantt)'
    _order = 'sequence asc'

    production_id = fields.Many2one('mrp.production', 'Orden de Producción', ondelete='cascade')
    sequence = fields.Integer('Secuencia', default=10)
    process_template_id = fields.Many2one('impr.process.template', 'Proceso')
    name = fields.Char('Nombre', compute='_compute_name', store=True, readonly=False)
    duration_days = fields.Integer('Duración (días)', required=True, default=1)
    people_required = fields.Integer('Personas', required=True, default=1)
    delay_days = fields.Integer('Días espera desde proceso anterior', default=1)
    date_start = fields.Date('Fecha inicio', compute='_compute_dates', store=True)
    date_end = fields.Date('Fecha fin', compute='_compute_dates', store=True)
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('in_progress', 'En curso'),
        ('done', 'Completado'),
    ], string='Estado', default='pending')
    date_completed = fields.Datetime('Fecha completado')
    completed_by = fields.Many2one('res.users', 'Completado por')
    active = fields.Boolean('Activo', default=True)
    workcenter_id = fields.Many2one(
        'mrp.workcenter', 'Centro de trabajo',
        help='Centro de trabajo donde se ejecuta este proceso.',
    )
    supplier_id = fields.Many2one(
        'res.partner', 'Proveedor subcontratación',
        help='Proveedor para servicios de terceros. Se usa al crear la OC automática.',
    )
    purchase_order_id = fields.Many2one(
        'purchase.order', 'Orden de Compra', readonly=True,
        help='OC generada automáticamente al iniciar un proceso de terceros.',
    )
    qty_produced = fields.Float(
        'Cant. procesada', digits=(12, 2),
        help='Cantidad real procesada por el operario.',
    )
    qty_waste = fields.Float(
        'Merma real', digits=(12, 2),
        help='Cantidad descartada como merma en este proceso.',
    )
    waste_pct = fields.Float(
        '% Merma', digits=(12, 2),
        compute='_compute_waste_pct', store=True,
        help='Porcentaje de merma: merma_real / (procesada + merma) * 100.',
    )
    # ── Costeo desde la cotización ─────────────────────────────────────
    # cost_total se carga al crear el proceso desde la quote (_create_processes_from_quote)
    # y queda fijo como snapshot histórico del costo planificado de ese paso.
    cost_total = fields.Float(
        'Costo planificado', digits=(12, 2),
        help='Monto de la sección de la cotización correspondiente a este proceso '
             '(papel, offset, doblado, etc.). Snapshot del momento de liberación.',
    )
    pct_total = fields.Float(
        '% del total', digits=(12, 2),
        compute='_compute_pct_total', store=True,
        help='Participación del costo de este proceso en el precio final de la '
             'cotización (sin IGV).',
    )

    @api.depends('cost_total', 'production_id.impr_quote_id.precio_final')
    def _compute_pct_total(self):
        for rec in self:
            quote = rec.production_id.impr_quote_id if rec.production_id else None
            base = quote.precio_final if quote else 0
            rec.pct_total = (rec.cost_total / base * 100) if base else 0.0

    @api.depends('qty_produced', 'qty_waste')
    def _compute_waste_pct(self):
        for rec in self:
            total = rec.qty_produced + rec.qty_waste
            rec.waste_pct = (rec.qty_waste / total * 100) if total else 0.0

    @api.depends('process_template_id')
    def _compute_name(self):
        for rec in self:
            if rec.process_template_id and not rec.name:
                rec.name = rec.process_template_id.name

    @api.onchange('process_template_id')
    def _onchange_process_template(self):
        if self.process_template_id:
            if not self.name:
                self.name = self.process_template_id.name
            if self.process_template_id.workcenter_id:
                self.workcenter_id = self.process_template_id.workcenter_id
            if self.process_template_id.people_default:
                self.people_required = self.process_template_id.people_default
            if self.process_template_id.duration_days_default:
                self.duration_days = self.process_template_id.duration_days_default

    @api.depends('production_id.date_start', 'sequence', 'duration_days', 'delay_days',
                 'production_id.process_ids.duration_days',
                 'production_id.process_ids.delay_days',
                 'production_id.process_ids.sequence')
    def _compute_dates(self):
        for rec in self:
            if not rec.production_id or not rec.production_id.date_start:
                rec.date_start = False
                rec.date_end = False
                continue

            base_date = rec.production_id.date_start.date() if hasattr(rec.production_id.date_start, 'date') else rec.production_id.date_start
            # Obtener todos los procesos anteriores ordenados por secuencia
            previous = rec.production_id.process_ids.filtered(
                lambda p: p.sequence < rec.sequence and p.active
            ).sorted('sequence')

            # Calcular fecha inicio en cascada:
            # Para cada proceso anterior: sumar su duración.
            # Entre procesos: sumar el delay del proceso SIGUIENTE (no del primero).
            offset = 0
            for i, prev in enumerate(previous):
                offset += (prev.duration_days or 0)
                # El delay entre el proceso anterior y el siguiente
                # se toma del proceso siguiente en la cadena
                if i < len(previous) - 1:
                    next_prev = previous[i + 1]
                    offset += (next_prev.delay_days or 0)

            # Agregar el delay propio (espera desde el último proceso anterior)
            if previous:
                offset += (rec.delay_days or 0)

            rec.date_start = base_date + timedelta(days=offset)
            rec.date_end = rec.date_start + timedelta(days=max((rec.duration_days or 1) - 1, 0))

    def action_mark_done(self):
        """Marca el proceso como completado y pasa el siguiente a in_progress."""
        self.ensure_one()
        self.write({
            'state': 'done',
            'date_completed': fields.Datetime.now(),
            'completed_by': self.env.uid,
        })
        # Pasar el siguiente proceso a in_progress
        next_process = self.production_id.process_ids.filtered(
            lambda p: p.sequence > self.sequence and p.state == 'pending' and p.active
        ).sorted('sequence')
        if next_process:
            next_process[0].state = 'in_progress'
        return False

    def action_start(self):
        """Inicia el proceso (lo pone en curso).
        Si es un proceso de terceros (TERCERO), genera OC automática.
        """
        self.ensure_one()
        self.state = 'in_progress'
        # Auto-create Purchase Order for subcontracting processes
        if (self.process_template_id
                and self.process_template_id.code == 'TERCERO'):
            self._create_subcontracting_po()
        return False

    def _create_subcontracting_po(self):
        """Create a Purchase Order for a subcontracting process."""
        self.ensure_one()
        supplier = self.supplier_id
        if not supplier:
            raise UserError(_(
                'Debe seleccionar un proveedor de subcontratación '
                'para el proceso "%s" antes de iniciarlo.'
            ) % self.name)

        mo = self.production_id
        product = mo.product_id
        qty = mo.product_qty

        # Find or use the default purchase UoM
        uom = product.uom_id

        po_vals = {
            'partner_id': supplier.id,
            'origin': _('OP %s - %s') % (mo.name, self.name),
            'order_line': [(0, 0, {
                'product_id': product.id,
                'name': _('Servicio terceros: %s — %s') % (self.name, mo.name),
                'product_qty': qty,
                'product_uom': uom.id,
                'price_unit': 0.0,  # To be confirmed by purchasing
            })],
        }
        po = self.env['purchase.order'].create(po_vals)
        self.purchase_order_id = po.id
        return po
