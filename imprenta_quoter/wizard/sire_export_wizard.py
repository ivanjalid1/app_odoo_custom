import base64
import io
from datetime import date

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ImprSireExportWizard(models.TransientModel):
    _name = 'impr.sire.export.wizard'
    _description = 'Exportar registros SIRE para SUNAT'

    date_from = fields.Date(
        string='Fecha Desde',
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='Fecha Hasta',
        required=True,
        default=fields.Date.today,
    )
    register_type = fields.Selection(
        selection=[
            ('ventas', 'Registro de Ventas e Ingresos'),
            ('compras', 'Registro de Compras'),
        ],
        string='Tipo de Registro',
        required=True,
        default='ventas',
    )
    # Output fields
    file_data = fields.Binary(string='Archivo', readonly=True)
    file_name = fields.Char(string='Nombre del archivo', readonly=True)
    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('done', 'Generado'),
        ],
        default='draft',
    )

    def action_export(self):
        """Generate SIRE TXT file per SUNAT format.

        SIRE format is pipe-delimited (|) with the following fields:

        Registro de Ventas (RVIE 14.x):
            Periodo|CUO|Correlativo|Fecha Registro|Fecha Emision|Fecha Vencimiento|
            Tipo Comprobante|Serie|Numero|Numero Final|
            Tipo Doc Identidad Cliente|Numero Doc Cliente|
            Razon Social Cliente|CAR-SUNAT|Valor Facturado Exportacion|
            Base Imponible Gravada|Descuento Base Imponible|IGV|
            Descuento IGV|Monto Exonerado|Monto Inafecto|ISC|
            Base Imponible Arroz|IGV Arroz|ICBPER|Otros Tributos|
            Importe Total|Codigo Moneda|Tipo de Cambio|
            Fecha Emision Ref|Tipo Comprobante Ref|Serie Ref|Numero Ref|
            Estado|

        Registro de Compras (RCE 8.x):
            Periodo|CUO|Correlativo|Fecha Emision|Fecha Vencimiento|
            Tipo Comprobante|Serie|Numero|Numero Final|
            Tipo Doc Identidad Proveedor|RUC Proveedor|
            Razon Social Proveedor|CAR-SUNAT|
            Base Imponible Gravada|IGV|Base Imponible Gravada 2|IGV 2|
            Base Imponible Gravada 3|IGV 3|Monto No Gravado|ISC|ICBPER|
            Otros Tributos|Importe Total|Codigo Moneda|Tipo de Cambio|
            Fecha Emision Ref|Tipo Comprobante Ref|Serie Ref|
            Numero Ref Dep Aduanera|Numero Ref Dep Aduanera Anio|
            Fecha Detraccion|Numero Constancia Detraccion|
            Marca Retencion|Clasificacion Bienes|
            Estado|
        """
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(_('La fecha desde no puede ser mayor a la fecha hasta.'))

        # Determine move types based on register type
        if self.register_type == 'ventas':
            move_types = ('out_invoice', 'out_refund')
        else:
            move_types = ('in_invoice', 'in_refund')

        moves = self.env['account.move'].search([
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
            ('move_type', 'in', move_types),
            ('state', '=', 'posted'),
        ], order='invoice_date asc, name asc')

        if not moves:
            raise UserError(_(
                'No se encontraron comprobantes %s entre %s y %s.',
                'de venta' if self.register_type == 'ventas' else 'de compra',
                self.date_from.strftime('%d/%m/%Y'),
                self.date_to.strftime('%d/%m/%Y'),
            ))

        # Generate TXT content
        output = io.StringIO()
        periodo = self.date_from.strftime('%Y%m00')

        for idx, move in enumerate(moves, start=1):
            cuo = str(idx)
            correlativo = 'M1'

            partner = move.partner_id
            fecha_emision = move.invoice_date.strftime('%d/%m/%Y') if move.invoice_date else ''
            fecha_vencimiento = (
                move.invoice_date_due.strftime('%d/%m/%Y')
                if move.invoice_date_due else fecha_emision
            )
            # Fecha de registro: use impr_fecha_registro if set, else invoice_date
            fecha_registro_raw = (
                move.impr_fecha_registro
                if move.impr_fecha_registro
                else move.invoice_date
            )
            fecha_registro = fecha_registro_raw.strftime('%d/%m/%Y') if fecha_registro_raw else ''

            # Determine tipo de comprobante SUNAT
            tipo_comprobante = self._get_tipo_comprobante(move)

            # Parse serie and numero from move name (e.g. F001-00000123)
            serie, numero = self._parse_serie_numero(move.name)

            # Partner document type and number
            tipo_doc_identidad = self._get_tipo_doc_identidad(partner)
            num_doc = partner.vat or ''
            razon_social = (partner.name or '').replace('|', ' ')

            # CAR-SUNAT (Código de Autorización de Registro del SEE/SIRE)
            car_sunat = (move.impr_car_sunat or '').replace('|', ' ')

            # Amounts
            currency_code = move.currency_id.name or 'PEN'
            sign = -1 if move.move_type in ('out_refund', 'in_refund') else 1

            # Calculate tax base and IGV from invoice lines
            base_imponible = 0.0
            igv = 0.0
            monto_exonerado = 0.0
            monto_inafecto = 0.0

            for line in move.invoice_line_ids.filtered(lambda l: l.display_type == 'product'):
                line_taxes = line.tax_ids
                if line_taxes:
                    base_imponible += line.price_subtotal * sign
                else:
                    # Lines without tax - check if exonerated or unaffected
                    monto_inafecto += line.price_subtotal * sign

            igv = move.amount_tax * sign
            importe_total = move.amount_total * sign

            tipo_cambio = ''
            if currency_code != 'PEN':
                # Get exchange rate for the invoice date
                if move.invoice_date:
                    rate = self.env['res.currency.rate'].search([
                        ('currency_id', '=', move.currency_id.id),
                        ('name', '<=', move.invoice_date),
                        ('company_id', 'in', [move.company_id.id, False]),
                    ], limit=1, order='name desc')
                    if rate and rate.inverse_company_rate:
                        tipo_cambio = f'{rate.inverse_company_rate:.3f}'

            # Reference document (for credit/debit notes)
            fecha_ref = ''
            tipo_comp_ref = ''
            serie_ref = ''
            numero_ref = ''
            ref_move = None
            if move.move_type in ('out_refund', 'in_refund') and move.reversed_entry_id:
                ref_move = move.reversed_entry_id
            elif hasattr(move, 'debit_origin_id') and move.debit_origin_id:
                ref_move = move.debit_origin_id
            if ref_move:
                fecha_ref = (
                    ref_move.invoice_date.strftime('%d/%m/%Y')
                    if ref_move.invoice_date else ''
                )
                tipo_comp_ref = self._get_tipo_comprobante(ref_move)
                serie_ref, numero_ref = self._parse_serie_numero(ref_move.name)

            # Estado: 1 = activo
            estado = '1'

            if self.register_type == 'ventas':
                line_parts = [
                    periodo,                                    # Periodo
                    cuo,                                        # CUO
                    correlativo,                                # Correlativo
                    fecha_registro,                             # Fecha de registro (contabilización)
                    fecha_emision,                              # Fecha Emision comprobante
                    fecha_vencimiento,                          # Fecha Vencimiento
                    tipo_comprobante,                           # Tipo Comprobante
                    serie,                                      # Serie
                    numero,                                     # Numero
                    '',                                         # Numero Final (consolidado)
                    tipo_doc_identidad,                         # Tipo Doc Identidad
                    num_doc,                                    # Numero Doc
                    razon_social,                               # Razon Social
                    car_sunat,                                  # CAR-SUNAT (SEE/SIRE) — ranura única entre razón social e importe
                    f'{base_imponible:.2f}',                    # Base Imponible Gravada
                    '',                                         # Descuento Base Imponible
                    f'{igv:.2f}',                               # IGV
                    '',                                         # Descuento IGV
                    f'{monto_exonerado:.2f}',                   # Monto Exonerado
                    f'{monto_inafecto:.2f}',                    # Monto Inafecto
                    '',                                         # ISC
                    '',                                         # Base Imp Arroz
                    '',                                         # IGV Arroz
                    '',                                         # ICBPER
                    '',                                         # Otros Tributos
                    f'{importe_total:.2f}',                     # Importe Total
                    currency_code,                              # Codigo Moneda
                    tipo_cambio,                                # Tipo de Cambio
                    fecha_ref,                                  # Fecha Emision Ref
                    tipo_comp_ref,                              # Tipo Comprobante Ref
                    serie_ref,                                  # Serie Ref
                    numero_ref,                                 # Numero Ref
                    estado,                                     # Estado
                ]
            else:
                # Registro de Compras
                line_parts = [
                    periodo,                                    # Periodo
                    cuo,                                        # CUO
                    correlativo,                                # Correlativo
                    fecha_emision,                              # Fecha Emision
                    fecha_vencimiento,                          # Fecha Vencimiento
                    tipo_comprobante,                           # Tipo Comprobante
                    serie,                                      # Serie
                    numero,                                     # Numero
                    '',                                         # Numero Final
                    tipo_doc_identidad,                         # Tipo Doc Proveedor
                    num_doc,                                    # RUC Proveedor
                    razon_social,                               # Razon Social
                    car_sunat,                                  # CAR-SUNAT (SEE/SIRE)
                    f'{base_imponible:.2f}',                    # Base Imponible Gravada
                    f'{igv:.2f}',                               # IGV
                    '',                                         # Base Imp Gravada 2
                    '',                                         # IGV 2
                    '',                                         # Base Imp Gravada 3
                    '',                                         # IGV 3
                    f'{monto_inafecto:.2f}',                    # Monto No Gravado
                    '',                                         # ISC
                    '',                                         # ICBPER
                    '',                                         # Otros Tributos
                    f'{importe_total:.2f}',                     # Importe Total
                    currency_code,                              # Codigo Moneda
                    tipo_cambio,                                # Tipo de Cambio
                    fecha_ref,                                  # Fecha Emision Ref
                    tipo_comp_ref,                              # Tipo Comp Ref
                    serie_ref,                                  # Serie Ref
                    numero_ref,                                 # Numero Ref (Dep Aduanera)
                    '',                                         # Anio Dep Aduanera
                    # Detracción SPOT — campos calculados por imprenta_quoter
                    (
                        move.impr_detraccion_fecha_pago.strftime('%d/%m/%Y')
                        if move.impr_detraccion_pagada and move.impr_detraccion_fecha_pago
                        else ''
                    ),                                          # Fecha Detraccion
                    (
                        move.impr_detraccion_nro_constancia or ''
                        if move.impr_detraccion_pagada
                        else ''
                    ),                                          # Num Constancia Detraccion
                    '',                                         # Marca Retencion
                    '',                                         # Clasificacion Bienes
                    estado,                                     # Estado
                ]

            output.write('|'.join(line_parts) + '|\n')

        # Generate file
        content = output.getvalue()
        output.close()

        # File naming per SUNAT convention
        # LE + RUC + YYYYMM00 + type_code + indicator + .txt
        company_vat = self.env.company.vat or '00000000000'
        if self.register_type == 'ventas':
            type_code = '140100'  # 14.1 Registro de Ventas
        else:
            type_code = '080100'  # 8.1 Registro de Compras

        file_name = f'LE{company_vat}{periodo}{type_code}00{1 if moves else 0}11.txt'

        file_data = base64.b64encode(content.encode('utf-8'))

        self.write({
            'file_data': file_data,
            'file_name': file_name,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _get_tipo_comprobante(self, move):
        """Determina tipo SUNAT: 01=Factura, 03=Boleta, 07=NC, 08=ND.

        Common codes:
            01 - Factura
            03 - Boleta de Venta
            07 - Nota de Credito
            08 - Nota de Debito
            14 - Recibo por Servicios Publicos
            91 - Comprobante de No Domiciliado
        """
        if move.move_type in ('out_refund', 'in_refund'):
            return '07'  # Nota de Crédito
        # Nota de débito: tiene origen en otra factura (debit_origin_id en Odoo 18)
        if hasattr(move, 'debit_origin_id') and move.debit_origin_id:
            return '08'  # Nota de Débito
        # Distinguish Factura vs Boleta by journal name/code
        if move.journal_id and move.journal_id.name:
            name_upper = move.journal_id.name.upper()
            if 'BOLETA' in name_upper or 'B001' in name_upper or 'B0' in name_upper:
                return '03'  # Boleta
        # Fall back to move name prefix
        name = move.name or ''
        if name.upper().startswith('B'):
            return '03'  # Boleta
        # Default to factura
        return '01'

    def _parse_serie_numero(self, name):
        """Parse invoice name into serie and numero.

        Expected format: F001-00000123 or B001-00000456
        """
        if not name:
            return ('', '')
        parts = name.split('-', 1)
        if len(parts) == 2:
            return (parts[0].strip(), parts[1].strip())
        return (name, '')

    def _get_tipo_doc_identidad(self, partner):
        """Return SUNAT identity document type code.

        Common codes:
            0 - Otros
            1 - DNI
            4 - Carnet de Extranjeria
            6 - RUC
            7 - Pasaporte
        """
        vat = partner.vat or ''
        if len(vat) == 11:
            return '6'  # RUC
        if len(vat) == 8:
            return '1'  # DNI
        return '0'  # Otros
