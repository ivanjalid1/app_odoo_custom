import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    process_ids = fields.One2many(
        'impr.production.process', 'production_id',
        string='Procesos de producción'
    )
    impr_quote_id = fields.Many2one('impr.print.quote', 'Cotización Imprenta', readonly=True)
    impr_wip_move_id = fields.Many2one(
        'account.move', 'Asiento WIP', readonly=True,
        help='Asiento contable de cierre WIP generado al completar la OP.',
    )
    invoice_ids = fields.One2many(
        'account.move', 'impr_production_id',
        string='Facturas',
    )
    invoice_count = fields.Integer(
        compute='_compute_invoice_count',
        string='Nº Facturas',
    )

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Facturas'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('impr_production_id', '=', self.id)],
            'context': {'default_impr_production_id': self.id},
        }

    def button_mark_done(self):
        """Override to:
          - marcar procesos Gantt pendientes como done (la OP se cierra → los
            procesos de plan también se dan por terminados)
          - generar asiento WIP
        """
        res = super().button_mark_done()
        now = fields.Datetime.now()
        for production in self:
            pending = production.process_ids.filtered(
                lambda p: p.state in ('pending', 'in_progress') and p.active
            )
            if pending:
                pending.write({
                    'state': 'done',
                    'date_completed': now,
                    'completed_by': self.env.user.id,
                })
                _logger.info(
                    'OP %s: %d proceso(s) Gantt marcado(s) como done al cerrar OP',
                    production.name, len(pending),
                )
            production._create_wip_journal_entry()
        return res

    def _create_wip_journal_entry(self):
        """Create the WIP closing journal entry:
        Debit:  Productos Terminados (21 - Productos Terminados)
        Credit: WIP - Productos en Proceso (23 - Productos en Proceso)

        Uses l10n_pe chart account codes:
        - 2111 Productos manufacturados (Productos Terminados)
        - 2311 Productos en proceso de manufactura (WIP)
        """
        self.ensure_one()

        # Calculate the total cost of consumed raw materials as the entry amount
        amount = sum(
            move.quantity * move.product_id.standard_price
            for move in self.move_raw_ids.filtered(lambda m: m.state == 'done')
        )
        if amount <= 0:
            _logger.info(
                'OP %s: no WIP entry created (zero or negative amount)', self.name
            )
            return

        # Find accounts using code prefix lookup compatible with l10n_pe
        # Odoo 18: account.account uses company_ids (Many2many), not company_id
        company = self.company_id or self.env.company
        # Productos Terminados — account starting with '2111'
        finished_account = self.env['account.account'].search([
            ('code', '=like', '2111%'),
            ('company_ids', 'in', [company.id]),
        ], limit=1)
        if not finished_account:
            finished_account = self.env['account.account'].search([
                ('code', '=like', '2111%'),
            ], limit=1)
        # WIP — account starting with '2311'
        wip_account = self.env['account.account'].search([
            ('code', '=like', '2311%'),
            ('company_ids', 'in', [company.id]),
        ], limit=1)
        if not wip_account:
            wip_account = self.env['account.account'].search([
                ('code', '=like', '2311%'),
            ], limit=1)

        if not finished_account or not wip_account:
            _logger.warning(
                'OP %s: WIP journal entry skipped — missing accounts '
                '(2111*: %s, 2311*: %s). Configure l10n_pe chart of accounts.',
                self.name,
                finished_account.code if finished_account else 'NOT FOUND',
                wip_account.code if wip_account else 'NOT FOUND',
            )
            return

        # Use the stock valuation journal or a miscellaneous journal
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', company.id),
        ], limit=1)
        if not journal:
            _logger.warning(
                'OP %s: WIP journal entry skipped — no general journal found.',
                self.name,
            )
            return

        move_vals = {
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'ref': _('Cierre OP %s — WIP') % self.name,
            'line_ids': [
                (0, 0, {
                    'name': _('Productos Terminados — %s') % self.name,
                    'account_id': finished_account.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': _('WIP Productos en Proceso — %s') % self.name,
                    'account_id': wip_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        }
        account_move = self.env['account.move'].create(move_vals)
        account_move.action_post()
        self.impr_wip_move_id = account_move.id
        _logger.info(
            'OP %s: WIP journal entry %s created (amount: %.2f PEN)',
            self.name, account_move.name, amount,
        )
