from odoo import models, fields, api
from odoo.exceptions import UserError


class ResPartnerDetraccion(models.Model):
    _inherit = 'res.partner'

    impr_detraccion_id = fields.Many2one(
        'impr.detraccion.tipo',
        string='Detracción por defecto',
        ondelete='restrict',
        help='Tipo de detracción SUNAT que se propondrá automáticamente al registrar '
             'una factura de compra de este proveedor. Dejar vacío para usar la regla '
             'genérica (12% si total ≥ S/ 700).',
    )


class AccountMoveDetraccion(models.Model):
    _inherit = 'account.move'

    impr_detraccion_id = fields.Many2one(
        'impr.detraccion.tipo',
        string='Tipo de Detracción',
        tracking=True,
    )
    impr_detraccion_porcentaje = fields.Float(
        string='Porcentaje detracción (%)',
        compute='_compute_detraccion',
        store=True,
        digits=(5, 2),
    )
    impr_detraccion_monto = fields.Monetary(
        string='Monto detracción',
        compute='_compute_detraccion',
        store=True,
        currency_field='currency_id',
    )
    impr_monto_neto_proveedor = fields.Monetary(
        string='Neto a pagar al proveedor',
        compute='_compute_detraccion',
        store=True,
        currency_field='currency_id',
    )
    impr_detraccion_pagada = fields.Boolean(
        string='Detracción depositada',
        default=False,
        tracking=True,
    )
    impr_detraccion_fecha_pago = fields.Date(
        string='Fecha depósito detracción',
        tracking=True,
    )
    impr_detraccion_nro_constancia = fields.Char(
        string='N° Constancia SPOT',
        size=20,
        tracking=True,
    )

    @api.depends('impr_detraccion_id', 'impr_detraccion_id.porcentaje',
                 'impr_detraccion_id.umbral', 'amount_total')
    def _compute_detraccion(self):
        for move in self:
            tipo = move.impr_detraccion_id
            total = move.amount_total
            if tipo and total >= tipo.umbral:
                pct = tipo.porcentaje
                monto = round(total * pct / 100.0, 2)
            else:
                pct = 0.0
                monto = 0.0
            move.impr_detraccion_porcentaje = pct
            move.impr_detraccion_monto = monto
            move.impr_monto_neto_proveedor = total - monto

    def action_marcar_detraccion_pagada(self):
        for move in self:
            if not move.impr_detraccion_monto:
                raise UserError('Esta factura no tiene detracción calculada.')
            move.impr_detraccion_pagada = True
        return True

    def _proponer_detraccion_auto(self):
        """Propone detracción automáticamente según el proveedor. Prioridad:
        1) Tipo configurado en la ficha del proveedor (impr_detraccion_id)
        2) Fallback: código 037 "Demás servicios" 12% si total ≥ S/ 700
        Solo se auto-propone cuando el campo está vacío — el usuario siempre
        puede sobreescribirlo manualmente desde la pestaña Detracción SUNAT."""
        default_servicios = self.env.ref(
            'imprenta_quoter.detraccion_037',
            raise_if_not_found=False,
        )
        for move in self:
            if move.move_type not in ('in_invoice', 'in_refund'):
                continue
            if move.impr_detraccion_id:
                continue
            partner_default = (
                move.partner_id.impr_detraccion_id
                if move.partner_id else False
            )
            if partner_default:
                move.impr_detraccion_id = partner_default
                continue
            # Sin default configurado en el proveedor: regla genérica 12% ≥ S/ 700
            if move.amount_total < 700.0:
                continue
            if default_servicios:
                move.impr_detraccion_id = default_servicios

    @api.onchange('invoice_line_ids', 'move_type', 'amount_total', 'partner_id')
    def _onchange_proponer_detraccion(self):
        self._proponer_detraccion_auto()

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves.with_context(skip_detraccion_auto=True)._proponer_detraccion_auto()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if self.env.context.get('skip_detraccion_auto'):
            return res
        if any(k in vals for k in ('invoice_line_ids', 'move_type', 'line_ids', 'partner_id')):
            self.with_context(skip_detraccion_auto=True)._proponer_detraccion_auto()
        return res
