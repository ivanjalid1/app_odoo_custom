import logging

from odoo import models, fields, api
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ImprWipClosingWizard(models.TransientModel):
    _name = 'impr.wip.closing.wizard'
    _description = 'Cierre WIP Fin de Mes'

    date = fields.Date(
        'Fecha de cierre',
        required=True,
        default=fields.Date.today,
    )
    journal_id = fields.Many2one(
        'account.journal',
        'Diario',
        required=True,
        domain=[('type', '=', 'general')],
    )
    line_ids = fields.One2many(
        'impr.wip.closing.line',
        'wizard_id',
        'Órdenes de Producción',
    )

    # Computed totals for display
    total_consumed = fields.Float(
        'Total costo consumido',
        compute='_compute_totals',
        digits=(12, 2),
    )
    total_wip = fields.Float(
        'Total WIP a registrar',
        compute='_compute_totals',
        digits=(12, 2),
    )

    @api.depends('line_ids.consumed_cost', 'line_ids.wip_amount')
    def _compute_totals(self):
        for wizard in self:
            wizard.total_consumed = sum(wizard.line_ids.mapped('consumed_cost'))
            wizard.total_wip = sum(wizard.line_ids.mapped('wip_amount'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        # Auto-load open OPs that have consumed materials
        productions = self.env['mrp.production'].search([
            ('state', 'in', ['confirmed', 'progress', 'to_close']),
        ])
        lines = []
        for prod in productions:
            consumed_cost = sum(
                move.quantity * move.product_id.standard_price
                for move in prod.move_raw_ids.filtered(lambda m: m.state == 'done')
            )
            if consumed_cost > 0:
                lines.append((0, 0, {
                    'production_id': prod.id,
                    'consumed_cost': consumed_cost,
                    'wip_amount': consumed_cost,  # default: all consumed = WIP
                }))

        if lines:
            res['line_ids'] = lines

        # Default to first general journal
        journal = self.env['account.journal'].search(
            [('type', '=', 'general')], limit=1
        )
        if journal:
            res['journal_id'] = journal.id

        return res

    def action_confirm(self):
        self.ensure_one()

        active_lines = self.line_ids.filtered(lambda l: l.wip_amount > 0)
        if not active_lines:
            raise UserError('No hay importes WIP que procesar.')

        move_ids = []
        for line in active_lines:
            move = line._create_wip_entry(self.journal_id, self.date)
            if move:
                move_ids.append(move.id)
                line.production_id.impr_wip_move_id = move.id

        if not move_ids:
            raise UserError(
                'No se pudieron generar asientos WIP. '
                'Verifique que existan las cuentas contables 2311* y 60* '
                'en el plan contable de la empresa.'
            )

        _logger.info(
            'Cierre WIP %s: %d asientos creados por un total de %.2f PEN',
            self.date, len(move_ids), self.total_wip,
        )

        # Return list view of created journal entries
        return {
            'type': 'ir.actions.act_window',
            'name': 'Asientos WIP Generados',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', move_ids)],
            'target': 'current',
        }


class ImprWipClosingLine(models.TransientModel):
    _name = 'impr.wip.closing.line'
    _description = 'Línea Cierre WIP'

    wizard_id = fields.Many2one(
        'impr.wip.closing.wizard',
        ondelete='cascade',
    )
    production_id = fields.Many2one(
        'mrp.production',
        'Orden de Producción',
        readonly=True,
    )
    product_id = fields.Many2one(
        related='production_id.product_id',
        string='Producto',
        readonly=True,
    )
    state = fields.Selection(
        related='production_id.state',
        string='Estado',
        readonly=True,
    )
    consumed_cost = fields.Float(
        'Costo consumido',
        readonly=True,
        digits=(12, 2),
        help='Costo total de materias primas consumidas en esta OP hasta la fecha.',
    )
    wip_amount = fields.Float(
        'Costo en proceso al cierre',
        digits=(12, 2),
        help=(
            'Importe que permanece en proceso al cierre del mes. '
            'Por defecto = todo lo consumido. '
            'Ajustar si parte de la producción ya está finalizada.'
        ),
    )

    def _create_wip_entry(self, journal, date):
        """Generate the month-end WIP journal entry for one OP:
            Dr. 2311  Productos en proceso de manufactura  (WIP)
            Cr. 60xx  Compras / Materias Primas
        """
        self.ensure_one()

        company = self.production_id.company_id or self.env.company

        # WIP account: 2311 Productos en proceso de manufactura
        # Odoo 18: account.account usa company_ids (Many2many)
        wip_account = self.env['account.account'].search([
            ('code', '=like', '2311%'),
            ('company_ids', 'in', [company.id]),
        ], limit=1)
        if not wip_account:
            wip_account = self.env['account.account'].search([
                ('code', '=like', '2311%'),
            ], limit=1)

        # Raw material / purchases account: 60 Compras
        mp_account = self.env['account.account'].search([
            ('code', '=like', '60%'),
            ('company_ids', 'in', [company.id]),
        ], limit=1)
        if not mp_account:
            mp_account = self.env['account.account'].search([
                ('code', '=like', '60%'),
            ], limit=1)

        if not wip_account or not mp_account:
            raise UserError(
                f'OP {self.production_id.name}: No se encontraron las cuentas contables.\n'
                f'Se requiere una cuenta 2311* (WIP) y una cuenta 60* (Compras/MP).\n'
                f'Configure el plan contable peruano (l10n_pe).\n\n'
                f'2311*: {"OK — " + wip_account.code if wip_account else "NO ENCONTRADA"}\n'
                f'60*:   {"OK — " + mp_account.code if mp_account else "NO ENCONTRADA"}'
            )

        move_vals = {
            'journal_id': journal.id,
            'date': date,
            'ref': (
                f'Cierre WIP {date.strftime("%m/%Y")} — {self.production_id.name}'
            ),
            'line_ids': [
                (0, 0, {
                    'name': f'WIP en proceso — {self.production_id.name}',
                    'account_id': wip_account.id,
                    'debit': self.wip_amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f'Materia prima en proceso — {self.production_id.name}',
                    'account_id': mp_account.id,
                    'debit': 0.0,
                    'credit': self.wip_amount,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()

        _logger.info(
            'Cierre WIP: asiento %s creado para OP %s (%.2f PEN)',
            move.name, self.production_id.name, self.wip_amount,
        )
        return move
