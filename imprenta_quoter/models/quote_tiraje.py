import math

from odoo import models, fields, api


class ImprQuoteTiraje(models.Model):
    _name = 'impr.quote.tiraje'
    _description = 'Tiraje alternativo de cotización (permite ofrecer varias opciones al cliente)'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    tiraje = fields.Integer('Tiraje', required=True, default=0)
    pct_utilidad = fields.Float('Utilidad %', digits=(5, 2), default=26.0,
                                  help='Margen de utilidad para esta alternativa.')

    precio_total = fields.Float('Precio s/IGV', digits=(12, 2),
                                 compute='_compute_precio_alt', store=False)
    precio_unitario = fields.Float('P. Unitario s/IGV', digits=(12, 4),
                                    compute='_compute_precio_alt', store=False)
    precio_total_igv = fields.Float('Precio c/IGV', digits=(12, 2),
                                     compute='_compute_precio_alt', store=False)
    precio_unitario_igv = fields.Float('P. Unitario c/IGV', digits=(12, 4),
                                        compute='_compute_precio_alt', store=False)

    @api.depends(
        'tiraje', 'pct_utilidad',
        'quote_id.papel_ids.pliegos', 'quote_id.papel_ids.precio_unit',
        'quote_id.papel_ids.material_id', 'quote_id.papel_ids.demasia',
        'quote_id.papel_ids.paginas',
        'quote_id.placa_ids.subtotal',
        'quote_id.offset_ids.maqui', 'quote_id.offset_ids.factor',
        'quote_id.offset_ids.precio_unit',
        'quote_id.acabado_ids.precio_unit', 'quote_id.acabado_ids.clisse',
        'quote_id.acabado_ids.aplica_a', 'quote_id.acabado_ids.factor',
        'quote_id.doblado_ids.factor', 'quote_id.doblado_ids.precio_unit',
        'quote_id.alce_ids.factor', 'quote_id.alce_ids.precio_unit',
        'quote_id.cosido_ids.cuadernillo', 'quote_id.cosido_ids.precio_unit',
        'quote_id.troquelado_ids.factor', 'quote_id.troquelado_ids.precio_unit',
        'quote_id.troquelado_ids.c_fijo',
        'quote_id.encuadernado_ids.subtotal',
        'quote_id.corte_ids.tipo', 'quote_id.corte_ids.precio_unit',
        'quote_id.empaquetado_ids.tipo', 'quote_id.empaquetado_ids.precio_unit',
        'quote_id.empaquetado_ids.libros_x_caja',
        'quote_id.transporte_ids.precio_unit',
        'quote_id.peso_x_libro',
        'quote_id.pct_ggff', 'quote_id.pct_comision',
    )
    def _compute_precio_alt(self):
        for r in self:
            q = r.quote_id
            if not q or not r.tiraje:
                r.precio_total = 0
                r.precio_unitario = 0
                r.precio_total_igv = 0
                r.precio_unitario_igv = 0
                continue
            r.precio_total = q._simulate_precio(r.tiraje, r.pct_utilidad)
            r.precio_unitario = r.precio_total / r.tiraje if r.tiraje else 0
            r.precio_total_igv = r.precio_total * 1.18
            r.precio_unitario_igv = r.precio_unitario * 1.18
