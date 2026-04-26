import math
from odoo import models, fields, api
from .tipos_seccion import get_caratula_codes


class ImprQuotePlaca(models.Model):
    _name = 'impr.quote.placa'
    _description = 'Línea de placas en cotización'
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
                           help='Pliegos por libro = Pag / Rendim (del papel).')

    @api.depends('sequence', 'quote_id.papel_ids.sequence',
                 'quote_id.papel_ids.tipo', 'quote_id.papel_ids.material_id',
                 'quote_id.papel_ids.paginas', 'quote_id.papel_ids.aprovechamiento',
                 'quote_id.papel_ids.pliegos')
    def _compute_from_papel(self):
        for r in self:
            if not r.quote_id:
                r.tipo = 'interior'
                r.material_id = False
                r.pagina = 0
                r.aprovechamiento = 0
                r.pliegos = 0
                continue
            match = r.quote_id.papel_ids.filtered(lambda p: p.sequence == r.sequence)
            p = match[:1]
            r.tipo = p.tipo or 'interior'
            r.material_id = p.material_id.id if p.material_id else False
            r.pagina = p.paginas
            r.aprovechamiento = p.aprovechamiento
            r.pliegos = p.pliegos
    maqui = fields.Float('Máquina', digits=(12, 2), default=0.5,
                          help='Factor de máquina. 1=máquina pliego completo; 0.5=media máquina.')
    color_t = fields.Float('Color T', digits=(12, 2))
    color_r = fields.Float('Color R', digits=(12, 2))
    placas = fields.Float('Placas', digits=(12, 2), compute='_compute_placas', store=True)
    precio_unit = fields.Float('Precio Unitario', digits=(12, 2))
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.depends('color_t', 'color_r', 'pliegos', 'maqui', 'tipo', 'pagina', 'aprovechamiento')
    def _compute_placas(self):
        """Fórmula:
          - Carátula : placas = color_t + color_r
          - Interior : placas = (pliegos_full/maqui) × (color_t+color_r)
        Usa precisión completa de pliegos (pagina/rendim) para evitar error de redondeo.
        """
        caratula_codes = get_caratula_codes(self.env)
        for r in self:
            if r.tipo in caratula_codes:
                r.placas = (r.color_t or 0) + (r.color_r or 0)
                continue
            pliegos_full = r.pagina / r.aprovechamiento if r.aprovechamiento else 0
            if not r.maqui or not pliegos_full:
                r.placas = 0
                continue
            r.placas = (pliegos_full / r.maqui) * ((r.color_t or 0) + (r.color_r or 0))

    @api.depends('placas', 'precio_unit')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = r.placas * r.precio_unit
