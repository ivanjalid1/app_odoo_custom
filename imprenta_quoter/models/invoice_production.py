from odoo import models, fields


class AccountMove(models.Model):
    _inherit = 'account.move'

    impr_production_id = fields.Many2one(
        'mrp.production',
        string='Orden de Producción',
        domain=[('state', 'not in', ['cancel'])],
        tracking=True,
        index=True,
        help='Orden de Producción (OP) asociada a esta factura/bill.',
    )

    impr_fecha_registro = fields.Date(
        string='Fecha de registro',
        default=fields.Date.today,
        tracking=True,
        copy=False,
        help='Fecha en que se ingresó el comprobante al sistema (puede diferir de la fecha de emisión).',
    )

    impr_car_sunat = fields.Char(
        string='CAR-SUNAT',
        size=40,
        tracking=True,
        copy=False,
        help='Código de Autorización de Registro asignado por SUNAT al comprobante electrónico (SEE/SIRE). '
             'Ingresarlo manualmente al registrar el comprobante.',
    )
