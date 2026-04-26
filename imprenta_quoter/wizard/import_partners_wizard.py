import base64
import csv
import io
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ImprImportPartnersWizard(models.TransientModel):
    _name = 'impr.import.partners.wizard'
    _description = 'Importar clientes/proveedores desde CSV'

    import_type = fields.Selection([
        ('clientes', 'Clientes'),
        ('proveedores', 'Proveedores'),
    ], string='Tipo', required=True, default='clientes')

    file_data = fields.Binary('Archivo CSV', required=True)
    file_name = fields.Char('Nombre de archivo')

    delimiter = fields.Selection([
        (',', 'Coma (,)'),
        (';', 'Punto y coma (;)'),
        ('\t', 'Tabulador'),
    ], string='Separador', default=',', required=True)

    result_message = fields.Text('Resultado', readonly=True)
    state = fields.Selection([
        ('draft', 'Pendiente'),
        ('done', 'Importado'),
    ], default='draft')

    # ── Instrucciones ────────────────────────────────────────────────────
    @property
    def _column_help(self):
        return _(
            'Columnas requeridas: nombre, ruc\n'
            'Columnas opcionales: telefono, email, direccion, distrito, ciudad\n\n'
            'La primera fila debe ser el encabezado.\n'
            'Si el RUC ya existe, se actualiza el registro.'
        )

    def action_import(self):
        self.ensure_one()
        if not self.file_data:
            raise UserError(_('Seleccione un archivo CSV.'))

        try:
            raw = base64.b64decode(self.file_data)
            text = raw.decode('utf-8-sig')  # utf-8-sig maneja BOM de Excel
        except Exception:
            try:
                text = raw.decode('latin-1')
            except Exception as e:
                raise UserError(_('No se pudo leer el archivo: %s') % str(e))

        reader = csv.DictReader(io.StringIO(text), delimiter=self.delimiter)

        # Normalizar encabezados (strip + lower)
        rows = []
        for row in reader:
            rows.append({k.strip().lower(): (v or '').strip() for k, v in row.items()})

        if not rows:
            raise UserError(_('El archivo está vacío o no tiene filas de datos.'))

        required_cols = {'nombre'}
        missing = required_cols - set(rows[0].keys())
        if missing:
            raise UserError(_(
                'Columnas faltantes en el CSV: %s\n'
                'Columnas encontradas: %s'
            ) % (', '.join(missing), ', '.join(rows[0].keys())))

        is_customer = self.import_type == 'clientes'
        is_supplier = self.import_type == 'proveedores'

        created = 0
        updated = 0
        errors = []

        for i, row in enumerate(rows, start=2):
            nombre = row.get('nombre', '').strip()
            if not nombre:
                errors.append(_('Fila %d: nombre vacío, se omite.') % i)
                continue

            ruc = row.get('ruc', '').strip()
            telefono = row.get('telefono', '').strip()
            email = row.get('email', '').strip()
            direccion = row.get('direccion', '').strip()
            distrito = row.get('distrito', '').strip()
            ciudad = row.get('ciudad', 'Lima').strip() or 'Lima'

            # Buscar partner existente por RUC (vat) o nombre exacto
            partner = False
            if ruc:
                partner = self.env['res.partner'].search([('vat', '=', ruc)], limit=1)
            if not partner:
                partner = self.env['res.partner'].search([
                    ('name', '=', nombre),
                    ('company_type', '=', 'company'),
                ], limit=1)

            vals = {
                'name': nombre,
                'company_type': 'company',
                'is_company': True,
                'customer_rank': 1 if is_customer else 0,
                'supplier_rank': 1 if is_supplier else 0,
            }
            if ruc:
                vals['vat'] = ruc
            if telefono:
                vals['phone'] = telefono
            if email:
                vals['email'] = email
            if direccion:
                vals['street'] = direccion
            if distrito:
                vals['city'] = distrito
            # País Perú
            peru = self.env.ref('base.pe', raise_if_not_found=False)
            if peru:
                vals['country_id'] = peru.id

            try:
                if partner:
                    # Si ya existe pero es del otro tipo, sumar rank
                    if is_customer and partner.customer_rank == 0:
                        vals['customer_rank'] = 1
                    if is_supplier and partner.supplier_rank == 0:
                        vals['supplier_rank'] = 1
                    partner.write(vals)
                    updated += 1
                else:
                    self.env['res.partner'].create(vals)
                    created += 1
            except Exception as e:
                errors.append(_('Fila %d (%s): %s') % (i, nombre, str(e)))

        lines = [
            _('Importación completada:'),
            _('  Creados: %d') % created,
            _('  Actualizados: %d') % updated,
        ]
        if errors:
            lines.append(_('\nAdvertencias:'))
            lines.extend(errors[:20])
            if len(errors) > 20:
                lines.append(_('  ... y %d errores más.') % (len(errors) - 20))

        self.result_message = '\n'.join(lines)
        self.state = 'done'

        _logger.info(
            'Importación partners (%s): %d creados, %d actualizados, %d errores.',
            self.import_type, created, updated, len(errors),
        )

        # Volver a abrir el wizard para mostrar resultado
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
