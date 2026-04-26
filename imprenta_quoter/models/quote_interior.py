from odoo import models, fields


class ImprQuoteInterior(models.Model):
    _name = 'impr.quote.interior'
    _description = 'Interior de cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    name = fields.Char('Interior', required=True)
    aprovechamiento = fields.Float('Aprovechamiento', digits=(12, 2))
    material_id = fields.Many2one('impr.paper.material', 'Material del interior')
    colores = fields.Char('Colores del interior')
    paginas = fields.Integer('Páginas', default=0)
