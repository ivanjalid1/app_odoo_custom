"""
Actualización automática del tipo de cambio USD/PEN desde SUNAT
via apis.net.pe (mismo servicio usado en Odoo 15).

Token configurado en ir.config_parameter: indomin.api_token_integration
URL: https://api.apis.net.pe/v2/sunat/tipo-cambio
Cron: se ejecuta diariamente (configurado en data/tc_cron.xml)
"""
import logging
import urllib.request
import json
from datetime import date

from odoo import models, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TC_URL = 'https://api.apis.net.pe/v2/sunat/tipo-cambio'
TC_TOKEN_KEY = 'indomin.api_token_integration'


class ImprResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _impr_update_usd_rate(self):
        """
        Obtiene el TC USD/PEN del día desde apis.net.pe/SUNAT
        y actualiza res.currency.rate.
        Se llama desde un cron diario.
        """
        token = self.env['ir.config_parameter'].sudo().get_param(TC_TOKEN_KEY)
        if not token:
            _logger.warning('impr TC: token no configurado (%s)', TC_TOKEN_KEY)
            return

        try:
            req = urllib.request.Request(
                TC_URL,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {token}',
                }
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            _logger.error('impr TC: error consultando API: %s', e)
            return

        try:
            venta = float(data['precioVenta'])
            fecha = data.get('fecha', str(date.today()))
        except (KeyError, ValueError) as e:
            _logger.error('impr TC: respuesta inesperada %s → %s', data, e)
            return

        if venta <= 0:
            _logger.warning('impr TC: valor de venta inválido: %s', venta)
            return

        usd = self.search([('name', '=', 'USD')], limit=1)
        if not usd:
            _logger.warning('impr TC: moneda USD no encontrada')
            return

        # Odoo guarda el rate como 1/TC (USD→PEN significa rate = 1/venta)
        rate_value = 1.0 / venta

        existing = self.env['res.currency.rate'].search([
            ('currency_id', '=', usd.id),
            ('name', '=', fecha),
        ], limit=1)

        if existing:
            existing.rate = rate_value
            _logger.info('impr TC: actualizado %s → venta=%.4f (rate=%.6f)', fecha, venta, rate_value)
        else:
            self.env['res.currency.rate'].create({
                'currency_id': usd.id,
                'name': fecha,
                'rate': rate_value,
            })
            _logger.info('impr TC: creado %s → venta=%.4f (rate=%.6f)', fecha, venta, rate_value)
