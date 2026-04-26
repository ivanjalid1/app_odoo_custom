# Smart Print Quoter

Smart quoting and production-launch app for offset printing shops, built for **Odoo 18 Community**.

> Salesperson enters the book specs once. The system calculates paper, plates, machine passes, folding, gathering, sewing, binding, cutting, packaging, freight, markup, IGV and final unit price automatically — and on approval generates the Sales Order **and** the Manufacturing Order with the exact same components.

## Why this module

Most printing shops still quote in spreadsheets. A typical book quote has 12+ cost sections (paper, plates, offset, finishing, folding, gathering, sewing, troquel, binding, cuts, packaging, transport) plus a markup waterfall. Anything you re-type between the quote and the production order is a transcription error. This module:

* Replaces the spreadsheet with a structured ORM model.
* Exposes every formula as a stored compute — auditable per quote.
* Generates the SO + MO with the exact components calculated for **this** specific job, not from a generic BoM.
* Keeps the Peruvian invoicing layer (l10n_pe) intact.

## Features

| Section | Captured | Formula |
|---|---|---|
| Paper | per-section paper, pages, imposition, overage | `q_pliegos = (pag/rendim) × (run + overage)` |
| Plates | per-section colors front/back, machine factor | cover: `K+L`; interior: `(pages/maqui) × (K+L)` |
| Offset | per-section machine passes per millar | `ceil(((run+overage) × (pliegos/maqui)) / 1000)` |
| Cover finishing | per-line lamination, varnish, embossing | `ceil(q_pliegos/1000) × tariff + fixed` |
| Folding | per-section folding factor | `q_offset × factor` |
| Gathering | per-section gathering factor (variable) | `x_doblar × factor` |
| Sewing | per-section pages-per-signature | `(pages/sig) × (run + overage)` |
| Troquel | per-section factor | `factor × q_offset / 1000 + fixed` |
| Binding | hot melt / wire-O / sewn / etc. | flat per millar |
| Cutting | initial (resmas) + final (millars) | `Σ(q_pliegos / packs)` and `ceil(run/1000)` |
| Packaging | book sealing + boxing + box sealing | `ceil(run/1000)` and `ceil(run/books_per_box)` |
| Transport | tier table by total weight | by kg or fixed tier |
| Markup | GGFF · profit · commission (inclusive) | `subtotal / (1-r1) / (1-r2) / (1-r3)` |

## Auto-generation on approval

Pressing **Release** on an approved quote:
1. Creates a Sales Order with one line: product `Trabajo de Impresión`, qty = run, unit price = computed unit price.
2. Creates a Manufacturing Order with **the exact paper components** computed for this job (real `q_pliegos`, real UoMs).
3. Auto-populates production steps based on the populated sections (offset only if there are pliegos, folding only if applicable, hot melt only if a binding is selected, etc.).

## Installation

1. Drop the module folder into your `addons-path`.
2. Update apps list and install **Smart Print Quoter**.
3. Open *Configuration → Print Quoter → Paper Materials* and load your supplier catalog (the module ships with an empty catalog — every shop has its own pricing).
4. Open *Configuration → Print Quoter → Finishing Services* and load your tariffs.
5. (Optional) Configure Nubefact endpoint and SPOT detraction account numbers in *Settings → System Parameters*.

## Dependencies

`sale`, `mrp`, `stock`, `purchase`, `account`, `mail`, `contacts`, `l10n_pe`.

All Community Edition modules. No Enterprise required.

## Pricing model

* Paper: `precio_resma` is computed as `largo × ancho × gramaje × $kg × paquetes / 10⁷` (USD inc VAT). For cardboard (`unidad_paquete = 1`) the field is taken as $/unit directly.
* Final unit price is **net of IGV**. The 18 % IGV is added on top in the SO/Invoice via the standard `l10n_pe` tax mapping.

## Support

* Vendor: **Emprendemos tu Web**
* Website: <https://emprendemostuweb.com/>
* Email: [etwagency@proton.me](mailto:etwagency@proton.me)

## License

OPL-1 (Odoo Proprietary License). One license per database. Source code shipped — modify freely for your own usage. Redistribution prohibited.
