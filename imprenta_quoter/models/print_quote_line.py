from odoo import models, fields


class ImprPrintQuoteLine(models.Model):
    _name = 'impr.print.quote.line'
    _description = 'Línea de detalle de cotización'
    _order = 'sequence'

    quote_id = fields.Many2one('impr.print.quote', 'Cotización', ondelete='cascade')
    sequence = fields.Integer('Secuencia', default=10)
    name = fields.Char('Descripción')
    product_id = fields.Many2one('product.product', 'Producto')
    quantity = fields.Float('Cantidad')
    uom_id = fields.Many2one('uom.uom', 'UdM')
    unit_cost = fields.Float('Costo unitario')
    subtotal = fields.Float('Subtotal')
    line_type = fields.Selection([
        ('material', 'Material'),
        ('process', 'Proceso'),
        ('finishing', 'Acabado'),
    ], string='Tipo')
