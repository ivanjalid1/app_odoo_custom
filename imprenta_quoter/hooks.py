import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Assign Peruvian accounting accounts to product categories after install."""
    _assign_product_category_accounts(env)
    _configure_payment_terms_note(env)


def _assign_product_category_accounts(env):
    """
    Assign income/expense accounts to product categories.
    Uses l10n_pe chart of accounts (PUC Peru).
    Income: 7011 (Mercaderías) / 7041 (Servicios prestados a terceros)
    Expense: 6011 (Compras - Mercaderías)
    """
    company = env.company

    def find_account(code_prefix):
        # Odoo 18: account.account usa company_ids (Many2many)
        acc = env['account.account'].search([
            ('code', '=like', code_prefix + '%'),
            ('company_ids', 'in', [company.id]),
        ], limit=1)
        if not acc:
            acc = env['account.account'].search([
                ('code', '=like', code_prefix + '%'),
            ], limit=1)
        return acc

    # Income account for materials sold (70 - Ventas)
    income_account = (
        find_account('70111')
        or find_account('7011')
        or find_account('701')
    )
    # Expense/Cost account for materials purchased (60 - Compras)
    expense_account = (
        find_account('6011')
        or find_account('601')
        or find_account('60')
    )

    if not income_account:
        _logger.warning(
            'imprenta_quoter: No income account (701x) found — skipping category account setup'
        )
        return
    if not expense_account:
        _logger.warning(
            'imprenta_quoter: No expense account (601x) found — skipping category account setup'
        )
        return

    category_xmlids = [
        'imprenta_quoter.categ_papel_bond',
        'imprenta_quoter.categ_papel_book',
        'imprenta_quoter.categ_papel_couche_brillo',
        'imprenta_quoter.categ_papel_couche_mate',
        'imprenta_quoter.categ_duplex',
        'imprenta_quoter.categ_carton',
    ]

    for xmlid in category_xmlids:
        categ = env.ref(xmlid, raise_if_not_found=False)
        if categ:
            categ.write({
                'property_account_income_categ_id': income_account.id,
                'property_account_expense_categ_id': expense_account.id,
            })
            _logger.info(
                'imprenta_quoter: Category "%s" → income=%s, expense=%s',
                categ.name, income_account.code, expense_account.code,
            )

    # Service income account: 7041 (Servicios prestados a terceros) or fallback to 704/70
    service_income = (
        find_account('70411')
        or find_account('7041')
        or find_account('704')
        or income_account
    )

    trabajo = env.ref('imprenta_quoter.product_trabajo_impresion', raise_if_not_found=False)
    if trabajo and service_income:
        trabajo.write({
            'property_account_income_id': service_income.id,
        })
        _logger.info(
            'imprenta_quoter: "Trabajo de Impresión" → income=%s',
            service_income.code,
        )


def _configure_payment_terms_note(env):
    """Set company-level default payment term if not already configured."""
    company = env.company
    if not company.property_payment_term_id:
        contado = env.ref('imprenta_quoter.payment_term_contado', raise_if_not_found=False)
        if contado:
            company.write({'property_payment_term_id': contado.id})
            _logger.info('imprenta_quoter: Default payment term set to "Contado (Contra entrega)"')
