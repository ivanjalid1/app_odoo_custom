"""
Integración facturación electrónica SUNAT via Nubefact.
Extiende account.move para firmar y enviar comprobantes.
Requiere: certificado .pfx + token Nubefact.
Configurar en: Ajustes → Parámetros del sistema:
  impr.nubefact_token, impr.nubefact_url, impr.serie_factura, impr.serie_boleta
"""
from odoo import models, fields, api
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class ImprAccountMove(models.Model):
    """Extensión de facturas para EDI SUNAT via Nubefact"""
    _inherit = 'account.move'

    # Estado EDI
    edi_state = fields.Selection([
        ('not_sent',  'No enviado'),
        ('sent',      'Enviado'),
        ('accepted',  'Aceptado por SUNAT'),
        ('rejected',  'Rechazado'),
        ('cancelled', 'Anulado'),
    ], string='Estado SUNAT', default='not_sent', tracking=True)

    edi_sunat_hash = fields.Char('Hash SUNAT', readonly=True)
    edi_cdr_content = fields.Text('CDR (respuesta SUNAT)', readonly=True)
    edi_xml_content = fields.Text('XML UBL 2.1', readonly=True)
    edi_error_message = fields.Text('Error EDI', readonly=True)
    edi_send_date = fields.Datetime('Fecha envío SUNAT', readonly=True)

    # Campos SUNAT adicionales
    l10n_pe_edi_action_reason = fields.Char('Motivo (Nota Crédito/Débito)')

    def action_send_edi_sunat(self):
        """Firmar XML y enviar a SUNAT via Nubefact"""
        self.ensure_one()
        if self.edi_state == 'accepted':
            raise UserError('Este comprobante ya fue aceptado por SUNAT.')

        token = self.env['ir.config_parameter'].sudo().get_param('impr.nubefact_token')
        if not token:
            raise UserError(
                'Configure el Token de Nubefact en:\n'
                'Configuración → Técnico → Parámetros → impr.nubefact_token\n'
                'O en Configuración → Ajustes → sección Facturación Electrónica'
            )

        try:
            payload = self._build_nubefact_payload()
            response = self._send_to_nubefact(payload, token)
            self._process_nubefact_response(response)
        except Exception as e:
            self.edi_state = 'rejected'
            self.edi_error_message = str(e)
            _logger.error('Error EDI SUNAT: %s', e)
            raise UserError(f'Error al enviar a SUNAT:\n{e}')

    def _build_nubefact_payload(self):
        """Construye el JSON para Nubefact según tipo de comprobante"""
        company = self.company_id
        partner = self.partner_id

        # Tipo de comprobante
        tipo_map = {
            'out_invoice': '01' if partner.l10n_latam_identification_type_id.l10n_pe_vat_code == '6' else '03',
            'out_refund':  '07',
        }
        tipo = tipo_map.get(self.move_type, '01')

        serie_param = 'impr.serie_factura' if tipo == '01' else 'impr.serie_boleta'
        serie = self.env['ir.config_parameter'].sudo().get_param(serie_param, 'F001')

        payload = {
            'operacion': 'generar_comprobante',
            'tipo_de_comprobante': int(tipo),
            'serie': serie,
            'numero': int(self.name.split('/')[-1]) if '/' in self.name else 1,
            'sunat_transaction': 1,
            'cliente_tipo_de_documento': self._get_doc_type(partner),
            'cliente_numero_de_documento': partner.vat or '',
            'cliente_denominacion': partner.name,
            'cliente_direccion': partner.street or '',
            'cliente_email': partner.email or '',
            'fecha_de_emision': self.invoice_date.strftime('%d-%m-%Y') if self.invoice_date else '',
            'moneda': 'PEN' if self.currency_id.name == 'PEN' else 'USD',
            'tipo_de_cambio': '',
            'porcentaje_de_igv': 18.00,
            'total_gravada': self.amount_untaxed,
            'total_igv': self.amount_tax,
            'total': self.amount_total,
            'items': self._build_line_items(),
        }
        return payload

    def _get_doc_type(self, partner):
        """Tipo de documento SUNAT: 6=RUC, 1=DNI, 0=otros"""
        if partner.vat and len(partner.vat) == 11:
            return 6
        if partner.vat and len(partner.vat) == 8:
            return 1
        return 0

    def _build_line_items(self):
        items = []
        for line in self.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
            items.append({
                'unidad_de_medida': 'ZZ',
                'codigo': line.product_id.default_code or '',
                'descripcion': line.name or line.product_id.name,
                'cantidad': line.quantity,
                'valor_unitario': line.price_unit,
                'precio_unitario': line.price_unit * 1.18,
                'subtotal': line.price_subtotal,
                'tipo_de_igv': 1,
                'igv': line.price_subtotal * 0.18,
                'total': line.price_total,
            })
        return items

    def _send_to_nubefact(self, payload, token):
        """Envía a Nubefact via HTTP (requiere requests o urllib)"""
        import urllib.request
        url_base = self.env['ir.config_parameter'].sudo().get_param(
            'impr.nubefact_url', 'https://api.nubefact.com/api/v1')
        url = f'{url_base}/{self.company_id.vat}'

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={
            'Content-Type': 'application/json',
            'Authorization': f'Token token="{token}"',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode('utf-8'))

    def _process_nubefact_response(self, response):
        """Procesa respuesta de Nubefact y actualiza el registro"""
        self.edi_send_date = fields.Datetime.now()
        self.edi_cdr_content = json.dumps(response, ensure_ascii=False, indent=2)

        if response.get('aceptada_por_sunat') or response.get('estado') == 'Aceptado':
            self.edi_state = 'accepted'
            self.edi_sunat_hash = response.get('hash', '')
            _logger.info('Factura %s aceptada por SUNAT', self.name)
        elif response.get('error'):
            self.edi_state = 'rejected'
            self.edi_error_message = response.get('error', {}).get('mensaje', str(response))
        else:
            self.edi_state = 'sent'
