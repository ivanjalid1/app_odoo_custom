{
    'name': 'Smart Print Quoter',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing',
    'summary': 'Quoting and production-launch app for offset printing '
               'shops. Paper, plates, finishing, binding and cost '
               'calculation with auto-generation of Sales and '
               'Manufacturing Orders.',
    'description': """
Smart Print Quoter
==================

A complete quoting and production-launch app tailored for offset
printing shops. The salesperson enters book format, run size,
paper, colors and finishing. The module computes paper sheets,
plates, machine passes, folding, gathering, binding, weight,
packaging, freight, markup, IGV and final unit price automatically.

When approved, one click creates the Sales Order and Manufacturing
Order with the exact same materials and quantities. No double
entry, no transcription errors.

Highlights
----------
* Paper, plate, offset, finishing, folding, gathering, sewing,
  binding, cutting, packaging and transport sections covered with
  industry-standard formulas.
* Editable per-section overage, gathering factor and signature
  size for each interior.
* Built-in markup waterfall (overhead, profit, commission) with
  inclusive percentage calculation.
* Auto-creation of Sales Order and Manufacturing Order with the
  components computed for the specific job, not from a generic BoM.
* Multiple alternative run sizes per quote, each with its own
  re-calculated unit price.
* Localized for Peru (l10n_pe): IGV 18%, account chart, payment
  terms, SPOT detractions, SIRE export wizard.

Tested on Odoo 18 Community.
    """,
    'author': 'Emprendemos tu Web',
    'website': 'https://emprendemostuweb.com/',
    'support': 'etwagency@proton.me',
    'license': 'OPL-1',
    'price': 50.00,
    'currency': 'USD',
    'images': ['static/description/banner.png'],
    'depends': [
        'sale',
        'mrp',
        'stock',
        'purchase',
        'account',
        'mail',
        'contacts',
        'l10n_pe',
    ],
    'data': [
        # Security
        'security/ir.model.access.csv',
        # Data
        'data/sequence.xml',
        'data/uom_data.xml',
        'data/mrp_workcenter.xml',
        'data/paper_materials.xml',
        'data/product_data.xml',
        'data/finishing_services.xml',
        'data/process_templates.xml',
        'data/stock_config.xml',
        'data/account_config.xml',
        'data/product_accounts_config.xml',
        'data/tc_cron.xml',
        'data/section_types.xml',
        'data/detraccion_tipos.xml',
        # Views
        'views/paper_material_views.xml',
        'views/finishing_service_views.xml',
        'views/process_template_views.xml',
        'views/print_quote_views.xml',
        'views/production_process_views.xml',
        'views/invoice_production_views.xml',
        'views/invoice_edi_views.xml',
        'views/section_type_views.xml',
        'views/detraccion_tipo_views.xml',
        'views/detraccion_views.xml',
        'views/hide_unused_menus.xml',
        'views/account_menu_reorg.xml',
        # Wizards
        'wizard/sire_export_wizard_views.xml',
        'wizard/price_update_wizard_views.xml',
        'wizard/wip_closing_wizard_views.xml',
        'wizard/import_partners_wizard_views.xml',
        # Menus
        'views/menus.xml',
        # Reports
        'report/print_quote_report.xml',
        'report/print_quote_report_template.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'imprenta_quoter/static/src/css/ui.css',
            'imprenta_quoter/static/src/css/gantt.css',
            'imprenta_quoter/static/src/js/production_gantt.js',
            'imprenta_quoter/static/src/js/user_menu_cleanup.js',
            'imprenta_quoter/static/src/xml/production_gantt.xml',
        ],
    },
    'post_init_hook': 'post_init_hook',
    'installable': True,
    'application': True,
    'auto_install': False,
}
