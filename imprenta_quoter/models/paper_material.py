from odoo import models, fields, api


class ImprPaperMaterial(models.Model):
    _name = 'impr.paper.material'
    _description = 'Material de papel para impresión'
    _order = 'name'

    name = fields.Char('Nombre', required=True)
    largo = fields.Float('Largo (cm)', required=True, digits=(12, 2))
    ancho = fields.Float('Ancho (cm)', required=True, digits=(12, 2))
    gramaje = fields.Float('Gramaje (g/m²)', required=True, digits=(12, 2))
    precio_kg = fields.Float('Precio por Kg', required=True, digits=(12, 4))
    unidad_paquete = fields.Integer('Hojas por paquete', default=500)
    precio_resma_inc_igv = fields.Float(
        'Precio resma INC IGV (USD)',
        compute='_compute_precio_resma_inc_igv',
        digits=(12, 4),
        help='Precio total que vende la papelera por resma/paquete (USD inc IGV).',
    )
    product_id = fields.Many2one('product.product', 'Producto en inventario')
    uom_id = fields.Many2one('uom.uom', 'Unidad de medida')
    active = fields.Boolean('Activo', default=True)

    @api.depends('largo', 'ancho', 'gramaje', 'precio_kg', 'unidad_paquete')
    def _compute_precio_resma_inc_igv(self):
        for r in self:
            if r.unidad_paquete and r.unidad_paquete > 1:
                r.precio_resma_inc_igv = (
                    r.largo * r.ancho * (r.gramaje or 0)
                    * (r.precio_kg or 0) * r.unidad_paquete
                ) / 10_000_000
            else:
                r.precio_resma_inc_igv = r.precio_kg or 0
