from odoo import models, fields, api


# Mapea códigos del catálogo impr.finishing.service → llaves viejas de Selection
# (usado solo por la migración de datos; conservado para compatibilidad)
SERVICE_CODE_TO_TIPO = {
    'PLAST_BRILLO': 'plastificado_brillo',
    'PLAST_MATE': 'plastificado_mate',
    'BARNIZ_UV': 'uv_brillo',
    'BARNIZ_UV_MATE': 'uv_mate',
    'BARNIZ_BRILLO': 'barniz_brillo',
    'BARNIZ_MATE': 'barniz_mate',
    'BARNIZ_ACRILICO_BRILLO': 'barniz_acrilico_brillo',
    'BARNIZ_AC': 'barniz_acrilico_mate',
    'UV_BRILLO_SECTOR': 'uv_brillo_sector',
    'HOT_STAMPING': 'hot_stamping',
    'REPUJADO': 'repujado',
    'ESCARCHADO': 'escarchado',
}


class ImprQuoteAcabado(models.Model):
    _name = 'impr.quote.acabado'
    _description = 'Línea de acabado en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    service_id = fields.Many2one(
        'impr.finishing.service',
        string='Acabado',
        domain=[('categoria', '=', 'acabado'), ('active', '=', True)],
        help='Servicio de acabado del catálogo (editable en Configuración → Acabados).',
    )
    tipo = fields.Char('Descripción', compute='_compute_tipo_from_service', store=True, readonly=False)
    aplica_a = fields.Selection(
        selection=lambda self: (
            self.env['impr.section.type']._selection_tipos()
            + [('ninguno', 'No aplica')]
        ),
        string='Aplica a',
        default='caratula',
        required=True,
        help='Dónde se aplica este acabado. "No aplica" lo excluye del total.',
    )
    factor = fields.Float('Factor', digits=(12, 2), default=1.0)
    q_pliegos = fields.Float('Q Pliegos', digits=(12, 2),
                              compute='_compute_q_pliegos_from_offset',
                              store=True, readonly=False)
    clisse = fields.Float('Clissé', digits=(12, 2))
    tiraje = fields.Integer('Tiraje',
                             compute='_compute_tiraje_from_q',
                             store=True, readonly=False)
    precio_unit = fields.Float('Precio Unit.', digits=(12, 2))
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.depends('service_id')
    def _compute_tipo_from_service(self):
        for r in self:
            if r.service_id:
                r.tipo = r.service_id.name
            elif not r.tipo:
                r.tipo = ''

    @api.onchange('service_id')
    def _onchange_service_id(self):
        """Auto-rellena tarifa según catálogo."""
        if self.service_id:
            if self.service_id.price_type == 'unit':
                self.clisse = self.service_id.price or 0.0
            else:
                self.precio_unit = self.service_id.price or 0.0

    @api.depends('aplica_a',
                 'quote_id.offset_ids.tipo', 'quote_id.offset_ids.q_pliegos')
    def _compute_q_pliegos_from_offset(self):
        for r in self:
            if r.aplica_a and r.aplica_a != 'ninguno' and r.quote_id:
                match = r.quote_id.offset_ids.filtered(
                    lambda o, ap=r.aplica_a: o.tipo == ap)[:1]
                r.q_pliegos = match.q_pliegos if match else 0
            else:
                r.q_pliegos = 0

    @api.depends('q_pliegos')
    def _compute_tiraje_from_q(self):
        import math as m
        for r in self:
            r.tiraje = m.ceil(r.q_pliegos / 1000) if r.q_pliegos else 0

    @api.depends('tiraje', 'precio_unit', 'clisse', 'aplica_a')
    def _compute_subtotal(self):
        for r in self:
            if r.aplica_a == 'ninguno':
                r.subtotal = 0.0
            else:
                r.subtotal = (r.tiraje * r.precio_unit) + r.clisse
