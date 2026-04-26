import math

from odoo import models, fields, api


class ImprQuoteTroquelado(models.Model):
    _name = 'impr.quote.troquelado'
    _description = 'Línea de troquelado en cotización (por sección)'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)

    # tipo/material/pag/rendim/pliegos/maqui/q_hojas/q_pliegos vienen AUTOMÁTICAMENTE de papel+offset
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
                          compute='_compute_from_papel', store=True, readonly=True)
    q_hojas = fields.Float('Q hojas', digits=(12, 2),
                            compute='_compute_from_papel', store=True, readonly=True,
                            help='Q hojas del papel.')
    q_pliegos = fields.Float('Q Pliegos', digits=(12, 2),
                              compute='_compute_from_papel', store=True, readonly=True,
                              help='Q Pliegos del offset (Excel J87 = J32).')

    @api.depends('sequence',
                 'quote_id.papel_ids.sequence', 'quote_id.papel_ids.tipo',
                 'quote_id.papel_ids.material_id', 'quote_id.papel_ids.paginas',
                 'quote_id.papel_ids.aprovechamiento', 'quote_id.papel_ids.pliegos',
                 'quote_id.papel_ids.q_pliegos',
                 'quote_id.offset_ids.sequence', 'quote_id.offset_ids.maqui',
                 'quote_id.offset_ids.q_pliegos')
    def _compute_from_papel(self):
        for r in self:
            if not r.quote_id:
                r.tipo = 'interior'
                r.material_id = False
                r.pagina = 0
                r.aprovechamiento = 0
                r.pliegos = 0
                r.maqui = 0
                r.q_hojas = 0
                r.q_pliegos = 0
                continue
            match = r.quote_id.papel_ids.filtered(lambda p: p.sequence == r.sequence)[:1]
            r.tipo = match.tipo or 'interior'
            r.material_id = match.material_id.id if match.material_id else False
            r.pagina = match.paginas
            r.aprovechamiento = match.aprovechamiento
            r.pliegos = match.pliegos
            r.q_hojas = match.q_pliegos or 0
            off_match = r.quote_id.offset_ids.filtered(lambda o: o.sequence == r.sequence)[:1]
            r.maqui = off_match.maqui or 0
            r.q_pliegos = off_match.q_pliegos or 0

    factor = fields.Float('Factor', digits=(12, 2), default=0.0,
                           help='Factor de troquelado por sección. 0 = no se troquela esta sección.')
    c_fijo = fields.Float('C Fijo', digits=(12, 2),
                          help='Costo fijo adicional al troquelado (Excel L87).')
    tiraje = fields.Integer('Tiraje (millar)', compute='_compute_tiraje', store=True,
                             help='Excel M87 = ROUNDUP(K*J/1000, 0) = ceil(Factor × Q Pliegos / 1000).')
    precio_unit = fields.Float('Precio Unit. (S/./millar)', digits=(12, 2))
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.depends('factor', 'q_pliegos')
    def _compute_tiraje(self):
        for r in self:
            v = (r.factor or 0) * (r.q_pliegos or 0)
            r.tiraje = math.ceil(v / 1000) if v else 0

    @api.depends('tiraje', 'precio_unit', 'c_fijo')
    def _compute_subtotal(self):
        """Excel O87 = N*M + L → subtotal = tiraje × precio + c_fijo."""
        for r in self:
            r.subtotal = (r.tiraje * r.precio_unit) + (r.c_fijo or 0)
