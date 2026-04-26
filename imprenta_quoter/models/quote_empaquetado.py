import math
from odoo import models, fields, api


class ImprQuoteEmpaquetado(models.Model):
    _name = 'impr.quote.empaquetado'
    _description = 'Línea de empaquetado en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    tipo = fields.Selection([
        ('sellado_libro', 'Sellado de Libro'),
        ('caja', 'Caja'),
        ('sellado_caja', 'Sellado de Caja'),
    ], string='Tipo', default='sellado_libro')
    # Estos campos se pre-llenan desde la cotización al crear, editables para override
    peso_x_libro = fields.Float('Peso x libro en Kg', digits=(12, 2))
    peso_total = fields.Float('Peso Total Kg', digits=(12, 2))
    peso_max_caja = fields.Float('PesoxCaja', digits=(12, 2))
    libros_x_caja = fields.Integer('Libros x caja')

    # Pre-fill se hace via onchange al elegir tipo (no en create)
    cantidad = fields.Integer('Cantidad', default=0)
    precio_unit = fields.Float('P Unit', digits=(12, 2))
    subtotal = fields.Float('P Total', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.onchange('quote_id')
    def _onchange_quote_id_pesos(self):
        """Al agregar una nueva línea de Caja, prellenar peso x libro y peso total."""
        if not self.quote_id or self.tipo != 'caja':
            return
        if not self.peso_x_libro:
            self.peso_x_libro = self.quote_id.peso_x_libro or 0
        if not self.peso_total:
            self.peso_total = self.quote_id.peso_total or 0

    @api.onchange('tipo', 'peso_max_caja')
    def _onchange_tipo_fill(self):
        """Auto-fill según tipo (fórmulas Excel rows 107-109):
          Sellado de Libro (107): solo cantidad = K5/1000 (sin pesos)
          Caja (108): peso x libro, peso total, peso max caja, libros x caja, cantidad
          Sellado de Caja (109): solo cantidad = M108 (sin pesos)
        """
        if not self.quote_id:
            return
        q = self.quote_id
        tiraje = q.tiraje_principal or 0

        if self.tipo == 'sellado_libro':
            # Excel row 107: solo M (Cantidad), N, O. Sin pesos.
            self.peso_x_libro = 0
            self.peso_total = 0
            self.peso_max_caja = 0
            self.libros_x_caja = 0
            self.cantidad = math.ceil(tiraje / 1000) if tiraje else 0

        elif self.tipo == 'caja':
            # Excel row 108: única fila con todos los campos de peso.
            self.peso_x_libro = q.peso_x_libro or 0
            self.peso_total = q.peso_total or 0
            if not self.peso_max_caja:
                self.peso_max_caja = q.peso_max_caja or 12
            pxl = q.peso_x_libro or 0
            if pxl and self.peso_max_caja:
                self.libros_x_caja = int(self.peso_max_caja / pxl)
            if self.libros_x_caja and tiraje:
                self.cantidad = math.ceil(tiraje / self.libros_x_caja)

        elif self.tipo == 'sellado_caja':
            # Excel row 109: M109 = M108. Sin pesos.
            self.peso_x_libro = 0
            self.peso_total = 0
            self.peso_max_caja = 0
            self.libros_x_caja = 0
            caja = self.quote_id.empaquetado_ids.filtered(
                lambda e: e.tipo == 'caja')[:1]
            self.cantidad = caja.cantidad if caja else 0

    @api.depends('cantidad', 'precio_unit', 'quote_id.empaquetado_ids.cantidad',
                 'quote_id.empaquetado_ids.tipo')
    def _compute_subtotal(self):
        for r in self:
            # Sellado de Caja: cantidad siempre = cantidad de Caja (Excel M103=M102)
            if r.tipo == 'sellado_caja' and r.quote_id:
                caja = r.quote_id.empaquetado_ids.filtered(lambda e: e.tipo == 'caja')[:1]
                if caja and r.cantidad != caja.cantidad:
                    r.cantidad = caja.cantidad
            r.subtotal = (r.cantidad or 0) * (r.precio_unit or 0)
