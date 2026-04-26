import math
from odoo import models, fields, api


class ImprQuoteOffset(models.Model):
    _name = 'impr.quote.offset'
    _description = 'Línea de offset en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    # tipo/material/pag/rendim/pliegos vienen AUTOMÁTICAMENTE de papel (por sequence)
    tipo = fields.Selection(
        selection=lambda self: self.env['impr.section.type']._selection_tipos(),
        string='Tipo', compute='_compute_from_papel', store=True, readonly=True,
    )
    material_id = fields.Many2one('impr.paper.material', 'Material',
                                    compute='_compute_from_papel', store=True, readonly=True)
    pagina = fields.Integer('Página', compute='_compute_from_papel', store=True, readonly=True)
    aprovechamiento = fields.Float('Aprovechamiento', digits=(12, 2),
                                    compute='_compute_from_papel', store=True, readonly=True)
    pliegos = fields.Float('Pliegos/libro', digits=(12, 2),
                            compute='_compute_from_papel', store=True, readonly=True,
                            help='Pliegos por libro del PAPEL para esa sección.')
    q_hojas = fields.Float('Q hojas', digits=(12, 2),
                            compute='_compute_from_papel', store=True, readonly=True,
                            help='Q hojas del papel = pliegos × (tiraje + demasía) (Excel I32 = J8).')

    @api.depends('sequence', 'quote_id.papel_ids.sequence',
                 'quote_id.papel_ids.tipo', 'quote_id.papel_ids.material_id',
                 'quote_id.papel_ids.paginas', 'quote_id.papel_ids.aprovechamiento',
                 'quote_id.papel_ids.pliegos', 'quote_id.papel_ids.q_pliegos')
    def _compute_from_papel(self):
        for r in self:
            if not r.quote_id:
                r.tipo = 'interior'
                r.material_id = False
                r.pagina = 0
                r.aprovechamiento = 0
                r.pliegos = 0
                r.q_hojas = 0
                continue
            match = r.quote_id.papel_ids.filtered(lambda p: p.sequence == r.sequence)
            p = match[:1]
            r.tipo = p.tipo or 'interior'
            r.material_id = p.material_id.id if p.material_id else False
            r.pagina = p.paginas
            r.aprovechamiento = p.aprovechamiento
            r.pliegos = p.pliegos
            r.q_hojas = p.q_pliegos or 0
    demasia = fields.Float('Demasía', digits=(12, 2),
                            help='Demasía (en copias) de la sección de papel correspondiente.')
    # Maqui ahora se jala desde PLACAS (misma sección por sequence) — no editable acá.
    maqui = fields.Float('Máquina', digits=(12, 2),
                          compute='_compute_from_placa', store=True, readonly=True,
                          help='Factor de máquina. Heredado de PLACAS (misma sección).')
    factor = fields.Float('Factor', digits=(12, 2), default=1.0,
                           help='(Legado — sin uso en la fórmula actual. Excel J32=J8/F32.)')
    q_pliegos = fields.Float('Q Pliegos', digits=(12, 2), compute='_compute_q_pliegos', store=True,
                              help='Excel J32 = J8/F32 → q_pliegos_offset = q_pliegos_papel / maqui.')
    # Excel K32/L32 = K20/L20 → OFFSET Color T/R vienen automáticamente de PLACAS (misma sección)
    color_t = fields.Float('Color T', digits=(12, 2),
                            compute='_compute_from_placa', store=True, readonly=True)
    color_r = fields.Float('Color R', digits=(12, 2),
                            compute='_compute_from_placa', store=True, readonly=True)

    @api.depends('sequence', 'quote_id.placa_ids.sequence',
                 'quote_id.placa_ids.color_t', 'quote_id.placa_ids.color_r',
                 'quote_id.placa_ids.maqui')
    def _compute_from_placa(self):
        for r in self:
            if not r.quote_id:
                r.color_t = 0
                r.color_r = 0
                r.maqui = 0.5
                continue
            match = r.quote_id.placa_ids.filtered(lambda pl: pl.sequence == r.sequence)[:1]
            r.color_t = match.color_t or 0
            r.color_r = match.color_r or 0
            r.maqui = match.maqui or 0.5

    tiraje = fields.Integer('Tiraje (millar)', compute='_compute_tiraje', store=True,
                             help='Tiraje a facturar en millares de pliegos = ceil(Q Pliegos / 1000).')
    precio_unit = fields.Float('Precio Unitario', digits=(12, 2),
                                help='S/ por millar de pliegos.')
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.depends('sequence', 'maqui',
                 'quote_id.papel_ids.sequence', 'quote_id.papel_ids.q_pliegos')
    def _compute_q_pliegos(self):
        """Excel J32 = J8/F32 → q_pliegos_offset = q_pliegos_papel / maqui.
        Sin factor extra: el Excel usa pura división. Toma directamente el
        Q Pliegos del papel (que ya incluye demasía)."""
        for r in self:
            if not r.quote_id or not r.maqui:
                r.q_pliegos = 0
                continue
            papel = r.quote_id.papel_ids.filtered(lambda p: p.sequence == r.sequence)[:1]
            q_papel = papel.q_pliegos if papel else 0
            r.q_pliegos = q_papel / r.maqui

    @api.depends('q_pliegos')
    def _compute_tiraje(self):
        for r in self:
            r.tiraje = math.ceil(r.q_pliegos / 1000) if r.q_pliegos else 0

    @api.depends('tiraje', 'precio_unit')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = r.tiraje * r.precio_unit
