import math

from odoo import models, fields, api


class ImprQuoteEncuadernado(models.Model):
    _name = 'impr.quote.encuadernado'
    _description = 'Línea de encuadernado en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    service_id = fields.Many2one(
        'impr.finishing.service', string='Encuadernado',
        domain=[('categoria', '=', 'encuadernado'), ('active', '=', True)],
        help='Seleccionar del catálogo de encuadernados (editable en Configuración → Encuadernados).',
    )
    tipo = fields.Char('Tipo', default='Encuadernado')

    def _quote_tiraje(self):
        """Tiraje en millares (ceil(tiraje/1000)) — encuadernado se cobra per millar."""
        q = self.quote_id
        if not q:
            return 0
        tiraje = q.tiraje_principal or (q.tiraje_ids[0].tiraje if q.tiraje_ids else 0)
        return math.ceil(tiraje / 1000) if tiraje else 0

    @api.model
    def _default_cantidad(self):
        """Default: tiraje en millares desde el quote padre (via context default_quote_id)."""
        quote_id = self.env.context.get('default_quote_id')
        if not quote_id:
            return 0
        quote = self.env['impr.print.quote'].browse(quote_id).exists()
        if not quote:
            return 0
        tiraje = quote.tiraje_principal or (
            quote.tiraje_ids[0].tiraje if quote.tiraje_ids else 0)
        return math.ceil(tiraje / 1000) if tiraje else 0

    @api.onchange('service_id')
    def _onchange_service_id(self):
        """Al elegir un acabado del catálogo, copiar nombre, tarifa y tiraje."""
        if self.service_id:
            self.tipo = self.service_id.name
            if self.service_id.price and not self.precio_unit:
                self.precio_unit = self.service_id.price
            if not self.cantidad:
                self.cantidad = self._quote_tiraje()

    peso_x_libro = fields.Float('Peso x libro', digits=(12, 2))
    peso_total = fields.Float('Peso total', digits=(12, 2))
    peso_max_caja = fields.Float('Peso máx. caja', digits=(12, 2))
    libros_x_caja = fields.Integer('Libros x caja', default=0)
    cantidad = fields.Integer('Cantidad', default=_default_cantidad)
    precio_unit = fields.Float('Precio Unit.', digits=(12, 2))
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.depends('cantidad', 'precio_unit')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = r.cantidad * r.precio_unit
