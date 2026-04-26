"""
Extensión de product.category para Smart Print Quoter.
Asigna cuentas contables del PCGE peruano a cada categoría de producto.
Se llama via <function> en data/product_accounts_config.xml en cada -u.
"""
import logging
from odoo import models, api

_logger = logging.getLogger(__name__)


class ImprProductCategory(models.Model):
    _inherit = 'product.category'

    @api.model
    def _impr_setup_accounts(self):
        """
        Asigna cuentas de ingresos/gastos a categorías de productos según PCGE Perú.

        Ingresos (ventas):
          7021   → Productos terminados (libros impresos)
          70211  → Productos terminados terminados
          702211 → Libros

        Gastos (compras de materiales):
          60211  → Materias primas — papeles
          60212  → Materias primas — cartones/dúplex
          60311  → Materiales auxiliares — tintas
          60312  → Materiales auxiliares — barnices
          60315  → Materiales auxiliares — material para encuadernar
          6031   → Materiales auxiliares (fallback genérico)
          6021   → Materias primas (fallback genérico)
        """
        company = self.env.company

        def acct(code):
            """Busca una cuenta por código exacto."""
            # Odoo 18: account.account usa company_ids (m2m), no company_id
            acc = self.env['account.account'].search([
                ('code', '=', code),
                ('company_ids', 'in', [company.id]),
            ], limit=1)
            if not acc:
                # fallback: buscar sin filtro de empresa
                acc = self.env['account.account'].search(
                    [('code', '=', code)], limit=1)
            if not acc:
                _logger.warning('impr: cuenta %s no encontrada', code)
            return acc

        # ── Cuentas de ingresos ─────────────────────────────────────────────
        inc_libros = acct('702211') or acct('70211') or acct('7021')
        inc_default = acct('7021') or acct('70111') or acct('7011')

        # ── Cuentas de gastos ───────────────────────────────────────────────
        exp_papeles = acct('60211') or acct('6021')
        exp_cartones = acct('60212') or acct('6021')
        exp_barnices = acct('60312') or acct('6031')
        exp_tintas = acct('60311') or acct('6031')
        exp_encuadernado = acct('60315') or acct('6031')
        exp_default = acct('6021') or acct('6011')

        if not inc_default or not exp_default:
            _logger.error(
                'impr: No se encontraron cuentas base (7021/6021). '
                'Verificar que l10n_pe esté instalado correctamente.'
            )
            return

        # ── Mapeo categoría → (cuenta ingresos, cuenta gastos) ─────────────
        mapping = {
            # Categorías de papel → materia prima papeles
            'imprenta_quoter.categ_papel_bond':
                (inc_libros or inc_default, exp_papeles),
            'imprenta_quoter.categ_papel_book':
                (inc_libros or inc_default, exp_papeles),
            'imprenta_quoter.categ_papel_couche_brillo':
                (inc_libros or inc_default, exp_papeles),
            'imprenta_quoter.categ_papel_couche_mate':
                (inc_libros or inc_default, exp_papeles),
            # Cartones / Dúplex → materia prima cartones
            'imprenta_quoter.categ_carton':
                (inc_libros or inc_default, exp_cartones),
            'imprenta_quoter.categ_duplex':
                (inc_libros or inc_default, exp_cartones),
            # Categorías nativas de Odoo — fallback genérico
            'product.product_category_all':
                (inc_default, exp_default),
            'product.product_category_1':
                (inc_default, exp_default),
        }

        for xmlid, (income_acc, expense_acc) in mapping.items():
            categ = self.env.ref(xmlid, raise_if_not_found=False)
            if not categ:
                continue
            # property_account_*_categ_id are company_dependent — needs with_company()
            categ_ctx = categ.with_company(company)
            vals = {}
            if income_acc:
                vals['property_account_income_categ_id'] = income_acc.id
            if expense_acc:
                vals['property_account_expense_categ_id'] = expense_acc.id
            if vals:
                categ_ctx.sudo().write(vals)
                _logger.info(
                    'impr: Categoría "%s" → ingresos=%s, gastos=%s',
                    categ.complete_name,
                    income_acc.code if income_acc else '-',
                    expense_acc.code if expense_acc else '-',
                )

        _logger.info('impr: _impr_setup_accounts completado')

    @api.model
    def _impr_setup_journals_and_taxes(self):
        """
        Configura cuentas contables en diarios y taxes que no quedan correctos
        tras la instalación de l10n_pe en Odoo 18:

        1. Partner empresa → cuenta por cobrar 1213, cuenta por pagar 4212
        2. Diario Boletas (B001) → cuenta de ingresos 70211 (no 70 que es padre)
        3. IGV 18% incluido en precio → cuenta 40111
        4. Cuentas por cobrar/pagar en todos los partners sin asignación
        """
        company = self.env.company

        def acct(code):
            acc = self.env['account.account'].search(
                [('code', '=', code), ('company_ids', 'in', [company.id])], limit=1)
            if not acc:
                acc = self.env['account.account'].search(
                    [('code', '=', code)], limit=1)
            return acc

        # ── 1. Cuentas por cobrar/pagar por defecto de la empresa ─────────────
        # En Odoo 18 company_dependent=True fields se guardan como JSONB {"cid": id}
        # Hay que usar with_company para que el write quede en el contexto correcto
        receivable = acct('1213')
        payable = acct('4212')
        company_partner = company.partner_id.with_company(company)

        if receivable:
            company_partner.sudo().property_account_receivable_id = receivable
            _logger.info('impr: empresa → cta cobrar = 1213')
        if payable:
            company_partner.sudo().property_account_payable_id = payable
            _logger.info('impr: empresa → cta pagar = 4212')

        # También aplicar en todos los partners sin cuenta asignada (default)
        # Odoo usa la empresa como fallback; lo que realmente importa es el
        # default del plan contable, que se maneja a nivel de account.account type

        # ── 2. Diario Boletas (B001): cuenta default 70211 ──────────────────
        boletas_journal = self.env['account.journal'].search(
            [('code', '=', 'B001')], limit=1)
        inc_boleta = acct('70211') or acct('7021')
        if boletas_journal and inc_boleta:
            current = boletas_journal.default_account_id
            if not current or current.code == '70':
                boletas_journal.default_account_id = inc_boleta.id
                _logger.info('impr: Boletas journal → cuenta default = %s', inc_boleta.code)

        # ── 3. IGV 18% incluido en precio → cuenta 40111 ────────────────────
        igv_account = acct('40111') or acct('4011')
        if igv_account:
            igv_taxes = self.env['account.tax'].search([
                ('type_tax_use', 'in', ['sale', 'purchase']),
                ('active', '=', True),
                ('amount', '=', 18.0),
            ])
            for tax in igv_taxes:
                for line in tax.invoice_repartition_line_ids.filtered(
                        lambda l: l.repartition_type == 'tax' and not l.account_id):
                    line.account_id = igv_account.id
                    _logger.info(
                        'impr: Tax "%s" repartition → cuenta = %s', tax.name, igv_account.code)
                for line in tax.refund_repartition_line_ids.filtered(
                        lambda l: l.repartition_type == 'tax' and not l.account_id):
                    line.account_id = igv_account.id

        # ── 4. Bank account labels — leave generic; user renames after install ─

        # ── 5. Deprecar cuentas duplicadas (10413/10414) — vienen de l10n_pe pero no se usan
        for dup_code in ('10413', '10414'):
            dup_acc = acct(dup_code)
            if dup_acc and not dup_acc.deprecated:
                dup_acc.sudo().write({'deprecated': True})
                _logger.info('impr: cuenta %s marcada deprecated (duplicada)', dup_code)

        # ── 6. Categoría All / Expenses → cuenta gastos administrativos 632910 ─
        exp_gastos = acct('632910') or acct('6329') or acct('63')
        categ_expenses = self.env.ref('product.product_category_expense',
                                      raise_if_not_found=False)
        if not categ_expenses:
            categ_expenses = self.search([('complete_name', '=', 'All / Expenses')], limit=1)
        if categ_expenses and exp_gastos:
            inc_exp = acct('7021') or acct('7011')
            categ_exp_ctx = categ_expenses.with_company(company)
            vals = {'property_account_expense_categ_id': exp_gastos.id}
            if inc_exp:
                vals['property_account_income_categ_id'] = inc_exp.id
            categ_exp_ctx.sudo().write(vals)
            _logger.info('impr: All/Expenses → gasto=%s', exp_gastos.code)

        # ── 8. Cuentas de diferencia de tipo de cambio ──────────────────────
        # Odoo 18 pone por defecto 441000/641000 (genéricas)
        # PCGE correcto: 77611 (ganancia TC) / 67611 (pérdida TC)
        tc_ganancia = acct('77611') or acct('7761')
        tc_perdida  = acct('67611') or acct('6761')
        if tc_ganancia and tc_perdida:
            company.sudo().write({
                'income_currency_exchange_account_id':  tc_ganancia.id,
                'expense_currency_exchange_account_id': tc_perdida.id,
            })
            _logger.info(
                'impr: TC ganancia=%s pérdida=%s',
                tc_ganancia.code, tc_perdida.code)

        _logger.info('impr: _impr_setup_journals_and_taxes completado')
