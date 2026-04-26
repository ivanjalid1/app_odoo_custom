"""
GRE — Guía de Remisión Electrónica (SUNAT)
Modelo para gestionar las guías de remisión ligadas a entregas.
Integración con Nubefact tipo_de_comprobante=9 (GRE Remitente).
"""
from odoo import models, fields, api
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class ImprGRE(models.Model):
    _name = 'impr.gre'
    _description = 'Guía de Remisión Electrónica'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc'

    name = fields.Char('Número GRE', readonly=True, default='Nuevo')
    state = fields.Selection([
        ('draft',     'Borrador'),
        ('sent',      'Enviado a SUNAT'),
        ('accepted',  'Aceptado'),
        ('rejected',  'Rechazado'),
        ('cancelled', 'Anulado'),
    ], default='draft', tracking=True)

    # Fechas
    date_issue = fields.Date('Fecha de emisión', required=True,
                              default=fields.Date.today)
    date_transfer = fields.Date('Fecha de traslado', required=True,
                                 default=fields.Date.today)

    # Remitente (empresa configurada)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company,
                                  required=True)

    # Destinatario
    partner_id = fields.Many2one('res.partner', string='Destinatario', required=True)
    delivery_address = fields.Char('Dirección de entrega')

    # Motivo de traslado
    transfer_reason = fields.Selection([
        ('01', '01 - Venta'),
        ('02', '02 - Compra'),
        ('04', '04 - Traslado entre locales'),
        ('08', '08 - Importación'),
        ('09', '09 - Exportación'),
        ('13', '13 - Otros'),
    ], string='Motivo de traslado', default='01', required=True)

    # Transporte
    transport_mode = fields.Selection([
        ('01', '01 - Transporte público'),
        ('02', '02 - Transporte privado'),
    ], string='Modalidad de traslado', default='02')

    # Vehículo / conductor (transporte privado)
    vehicle_plate = fields.Char('Placa del vehículo')
    driver_name = fields.Char('Nombre del conductor')
    driver_doc = fields.Char('Documento del conductor (DNI/RUC)')

    # Transportista (transporte público)
    carrier_id = fields.Many2one('res.partner', string='Empresa transportista')

    # Carga
    gross_weight = fields.Float('Peso bruto total (kg)', digits=(10, 3))
    package_count = fields.Integer('Número de bultos')

    # Vinculaciones
    picking_id = fields.Many2one('stock.picking', string='Entrega vinculada')
    sale_order_id = fields.Many2one('sale.order', string='Orden de Venta')
    production_id = fields.Many2one('mrp.production', string='Orden de Producción')

    # Líneas de productos
    line_ids = fields.One2many('impr.gre.line', 'gre_id', string='Productos')

    # Respuesta SUNAT
    edi_state = fields.Selection([
        ('not_sent',  'No enviado'),
        ('sent',      'Enviado'),
        ('accepted',  'Aceptado'),
        ('rejected',  'Rechazado'),
    ], string='Estado SUNAT', default='not_sent')
    edi_hash = fields.Char('Hash SUNAT', readonly=True)
    edi_cdr = fields.Text('CDR SUNAT', readonly=True)
    edi_error = fields.Text('Error', readonly=True)
    edi_send_date = fields.Datetime('Fecha envío', readonly=True)
    edi_nubefact_link = fields.Char('Link Nubefact', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('impr.gre') or 'GRE-0001'
        return super().create(vals_list)

    def action_send_sunat(self):
        """Enviar GRE a SUNAT via Nubefact"""
        self.ensure_one()
        if self.edi_state == 'accepted':
            raise UserError('Esta GRE ya fue aceptada por SUNAT.')

        token = self.env['ir.config_parameter'].sudo().get_param('impr.nubefact_token')
        if not token:
            raise UserError(
                'Configure el Token de Nubefact en Ajustes → Facturación Electrónica.\n'
                'Pendiente: configurar token de Nubefact.'
            )

        try:
            payload = self._build_gre_payload()
            response = self._send_to_nubefact(payload, token)
            self._process_response(response)
        except Exception as e:
            self.edi_state = 'rejected'
            self.edi_error = str(e)
            raise UserError(f'Error al enviar GRE a SUNAT:\n{e}')

    def _build_gre_payload(self):
        return {
            'operacion': 'generar_comprobante',
            'tipo_de_comprobante': 9,  # GRE Remitente
            'serie': 'T001',
            'numero': int(self.name.split('-')[-1]) if '-' in self.name else 1,
            'fecha_de_emision': self.date_issue.strftime('%d-%m-%Y'),
            'fecha_de_traslado': self.date_transfer.strftime('%d-%m-%Y'),
            'motivo_de_traslado': self.transfer_reason,
            'modalidad_de_traslado': self.transport_mode,
            'peso_bruto': self.gross_weight,
            'numero_de_bultos': self.package_count,
            'remitente_tipo_de_documento': 6,
            'remitente_numero_de_documento': self.company_id.vat or '',
            'remitente_denominacion': self.company_id.name,
            'destinatario_tipo_de_documento': 6 if (self.partner_id.vat and len(self.partner_id.vat or '') == 11) else 1,
            'destinatario_numero_de_documento': self.partner_id.vat or '',
            'destinatario_denominacion': self.partner_id.name,
            'destinatario_direccion': self.delivery_address or self.partner_id.street or '',
            'vehiculo_placa': self.vehicle_plate or '',
            'conductor_documento': self.driver_doc or '',
            'conductor_denominacion': self.driver_name or '',
            'items': [{
                'unidad_de_medida': 'ZZ',
                'descripcion': line.product_id.name,
                'cantidad': line.qty,
            } for line in self.line_ids],
        }

    def _send_to_nubefact(self, payload, token):
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

    def _process_response(self, response):
        self.edi_send_date = fields.Datetime.now()
        self.edi_cdr = json.dumps(response, ensure_ascii=False, indent=2)
        self.edi_nubefact_link = response.get('enlace_del_pdf', '')
        if response.get('aceptada_por_sunat'):
            self.edi_state = 'accepted'
            self.edi_hash = response.get('hash', '')
            self.state = 'accepted'
        elif response.get('error'):
            self.edi_state = 'rejected'
            self.edi_error = response.get('error', {}).get('mensaje', str(response))
        else:
            self.edi_state = 'sent'
            self.state = 'sent'

    def action_cancel(self):
        """Anular GRE (requiere comunicar baja a SUNAT en máx. 24h)"""
        self.ensure_one()
        if self.edi_state == 'accepted':
            raise UserError(
                'Para anular una GRE ya aceptada por SUNAT debe comunicar\n'
                'la baja dentro de las 24 horas siguientes a la emisión.'
            )
        self.state = 'cancelled'
        self.edi_state = 'not_sent'


class ImprGRELine(models.Model):
    _name = 'impr.gre.line'
    _description = 'Línea de GRE'

    gre_id = fields.Many2one('impr.gre', ondelete='cascade')
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    description = fields.Char('Descripción')
    qty = fields.Float('Cantidad', default=1.0)
    uom_id = fields.Many2one('uom.uom', string='Unidad')
