from odoo import models, fields


class ImprFinishingService(models.Model):
    _name = 'impr.finishing.service'
    _description = 'Servicio de acabado de imprenta'
    _order = 'categoria, name'

    name = fields.Char('Nombre', required=True)
    code = fields.Char('Código', required=True)
    categoria = fields.Selection(
        [
            ('acabado', 'Acabados'),
            ('encuadernado', 'Encuadernados'),
            ('otros', 'Otros'),
        ],
        string='Categoría',
        default='acabado',
        required=True,
        help='Categoría que determina en qué sección de la cotización aparece: '
             'Acabados (carátula) o Encuadernados.',
    )
    active = fields.Boolean('Activo', default=True)
    price = fields.Float('Tarifa')
    price_type = fields.Selection([
        ('unit', 'Por unidad'),
        ('millar', 'Por millar'),
    ], string='Tipo de tarifa', default='millar')
    description = fields.Text('Descripción')
    account_id = fields.Many2one(
        'account.account',
        string='Cuenta contable',
        domain=[('deprecated', '=', False)],
        help='Cuenta de ingresos/costos para este servicio de acabado. '
             'Se usa en facturación cuando se registra este servicio.',
        company_dependent=True,
    )
    product_id = fields.Many2one(
        'product.product',
        string='Producto Odoo',
        domain=[('type', '=', 'service')],
        help='Producto de Odoo vinculado a este servicio para facturación estándar.',
    )
