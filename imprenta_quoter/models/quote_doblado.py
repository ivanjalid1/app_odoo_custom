import math
from odoo import models, fields, api


class ImprQuoteDoblado(models.Model):
    _name = 'impr.quote.doblado'
    _description = 'Línea de doblado en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    # tipo/material/pag/rendim/pliegos/q_hojas vienen AUTOMÁTICAMENTE de papel (por sequence)
    tipo = fields.Selection(
        selection=lambda self: self.env['impr.section.type']._selection_tipos(),
        string='Tipo', compute='_compute_from_papel', store=True, readonly=True,
    )
    material_id = fields.Many2one('impr.paper.material', 'Material',
                                    compute='_compute_from_papel', store=True, readonly=True)
    pagina = fields.Integer('Pag', compute='_compute_from_papel', store=True, readonly=True)
    aprovechamiento = fields.Float('Rendim', digits=(12, 2),
                                    compute='_compute_from_papel', store=True, readonly=True)
    pliegos = fields.Float('Pliegos/libro', digits=(12, 2),
                            compute='_compute_from_papel', store=True, readonly=True)
    maqui = fields.Float('Maqui', digits=(12, 2),
                          compute='_compute_from_papel', store=True, readonly=True,
                          help='Factor de máquina del offset de la sección (auto).')
    q_hojas = fields.Float('Q hojas', digits=(12, 2),
                            compute='_compute_from_papel', store=True, readonly=True,
                            help='Q hojas del papel (Excel G52 = J8).')

    @api.depends('sequence', 'quote_id.papel_ids.sequence',
                 'quote_id.papel_ids.tipo', 'quote_id.papel_ids.material_id',
                 'quote_id.papel_ids.paginas', 'quote_id.papel_ids.aprovechamiento',
                 'quote_id.papel_ids.pliegos', 'quote_id.papel_ids.q_pliegos',
                 'quote_id.offset_ids.sequence', 'quote_id.offset_ids.maqui')
    def _compute_from_papel(self):
        for r in self:
            if not r.quote_id:
                r.tipo = 'interior'
                r.material_id = False
                r.pagina = 0
                r.aprovechamiento = 0
                r.pliegos = 0
                r.q_hojas = 0
                r.maqui = 0
                continue
            match = r.quote_id.papel_ids.filtered(lambda p: p.sequence == r.sequence)
            p = match[:1]
            r.tipo = p.tipo or 'interior'
            r.material_id = p.material_id.id if p.material_id else False
            r.pagina = p.paginas
            r.aprovechamiento = p.aprovechamiento
            r.pliegos = p.pliegos
            r.q_hojas = p.q_pliegos or 0
            off_match = r.quote_id.offset_ids.filtered(lambda o: o.sequence == r.sequence)[:1]
            r.maqui = off_match.maqui or 0
    factor = fields.Float('Factor', digits=(12, 2), default=1.0,
                           help='Factor de doblado (1=32pág, 2=8pág, 4=4pág, etc).')
    q_pliegos = fields.Float('Q Pliegos', digits=(12, 2),
                              compute='_compute_q_pliegos_from_offset',
                              store=True, readonly=True,
                              help='Q Pliegos del offset para esta sección (auto).')

    @api.depends('sequence', 'quote_id.offset_ids.sequence',
                 'quote_id.offset_ids.q_pliegos')
    def _compute_q_pliegos_from_offset(self):
        for r in self:
            if not r.quote_id:
                r.q_pliegos = 0
                continue
            match = r.quote_id.offset_ids.filtered(lambda o: o.sequence == r.sequence)
            r.q_pliegos = match[:1].q_pliegos or 0
    x_doblar = fields.Float('x doblar', digits=(12, 2), compute='_compute_x_doblar', store=True,
                             help='Total doblados = Q Pliegos × Factor.')
    tiraje = fields.Integer('Tiraje (millar)', compute='_compute_tiraje', store=True,
                             help='ceil(x_doblar / 1000).')
    precio_unit = fields.Float('Precio Unitario', digits=(12, 2),
                                help='S/ por millar de doblados.')
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.depends('q_pliegos', 'factor')
    def _compute_x_doblar(self):
        for r in self:
            r.x_doblar = (r.q_pliegos or 0) * (r.factor or 0)

    @api.depends('x_doblar')
    def _compute_tiraje(self):
        for r in self:
            r.tiraje = math.ceil(r.x_doblar / 1000) if r.x_doblar else 0

    @api.depends('tiraje', 'precio_unit')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = r.tiraje * r.precio_unit
