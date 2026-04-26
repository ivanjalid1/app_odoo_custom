import math
from odoo import models, fields, api


class ImprQuoteCorte(models.Model):
    _name = 'impr.quote.corte'
    _description = 'Línea de corte (inicial/final) en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    tipo = fields.Selection([
        ('inicial', 'Corte Inicial'),
        ('final', 'Corte Final'),
    ], string='Tipo', required=True, default='inicial')
    # Cantidad auto-calculada (recomputa cuando cambian papeles o tiraje):
    #   Inicial: Σ(q_pliegos / paquetes) = resmas totales (Excel M96)
    #   Final:   ceil(tiraje / 1000)      = millares (Excel M97)
    cantidad = fields.Float('Cantidad', digits=(12, 2),
                             compute='_compute_cantidad', store=True,
                             help='Inicial: resmas. Final: millares. Recalcula '
                                  'automáticamente cuando agregás papeles o '
                                  'cambiás el tiraje.')
    precio_unit = fields.Float('Precio Unit.', digits=(12, 2),
                                help='Inicial: S/ por resma. Final: S/ por millar.')
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.depends('tipo',
                 'quote_id.papel_ids.q_pliegos', 'quote_id.papel_ids.paquetes',
                 'quote_id.tiraje_principal')
    def _compute_cantidad(self):
        """Cantidad según tipo:
          Inicial: Σ(q_pliegos_i / paquetes_i) de todos los papeles
          Final:   ceil(tiraje / 1000)
        """
        for r in self:
            if not r.quote_id:
                r.cantidad = 0
                continue
            if r.tipo == 'inicial':
                total = 0.0
                for p in r.quote_id.papel_ids:
                    if p.paquetes:
                        total += (p.q_pliegos or 0) / p.paquetes
                r.cantidad = total
            elif r.tipo == 'final':
                tiraje = r.quote_id.tiraje_principal or 0
                r.cantidad = math.ceil(tiraje / 1000) if tiraje else 0
            else:
                r.cantidad = 0

    @api.depends('cantidad', 'precio_unit')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = (r.cantidad or 0) * (r.precio_unit or 0)
