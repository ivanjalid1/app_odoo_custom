import math
from odoo import models, fields, api


class ImprQuoteCosido(models.Model):
    _name = 'impr.quote.cosido'
    _description = 'Línea de cosido en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    # tipo/material/pag/rendim/pliegos/demasia vienen AUTOMÁTICAMENTE de papel (por sequence)
    tipo = fields.Selection(
        selection=lambda self: self.env['impr.section.type']._selection_tipos(),
        string='Tipo', compute='_compute_from_papel', store=True, readonly=True,
    )
    material_id = fields.Many2one('impr.paper.material', 'Material',
                                    compute='_compute_from_papel', store=True, readonly=True)
    pagina = fields.Integer('Pag', compute='_compute_from_papel', store=True, readonly=True)
    aprovechamiento = fields.Float('Rendim', digits=(12, 2),
                                    compute='_compute_from_papel', store=True, readonly=True)
    pliegos = fields.Float('Pliegos', digits=(12, 2),
                            compute='_compute_from_papel', store=True, readonly=True,
                            help='Pliegos por libro (= Pag/Rendim).')
    demasia = fields.Float('Demasia', digits=(12, 2),
                            compute='_compute_from_papel', store=True, readonly=True,
                            help='Demasía de la sección de papel.')
    tiraje_libro = fields.Integer('tiraje', compute='_compute_from_papel',
                                   store=True, readonly=True,
                                   help='Tiraje del libro (de la cabecera del presupuesto).')

    @api.depends('sequence',
                 'quote_id.papel_ids.sequence', 'quote_id.papel_ids.tipo',
                 'quote_id.papel_ids.material_id', 'quote_id.papel_ids.paginas',
                 'quote_id.papel_ids.aprovechamiento', 'quote_id.papel_ids.pliegos',
                 'quote_id.papel_ids.demasia',
                 'quote_id.tiraje_principal')
    def _compute_from_papel(self):
        for r in self:
            if not r.quote_id:
                r.tipo = 'interior'
                r.material_id = False
                r.pagina = 0
                r.aprovechamiento = 0
                r.pliegos = 0
                r.demasia = 0
                r.tiraje_libro = 0
                continue
            match = r.quote_id.papel_ids.filtered(lambda p: p.sequence == r.sequence)
            p = match[:1]
            r.tipo = p.tipo or 'interior'
            r.material_id = p.material_id.id if p.material_id else False
            r.pagina = p.paginas
            r.aprovechamiento = p.aprovechamiento
            r.pliegos = p.pliegos
            r.demasia = p.demasia or 0
            r.tiraje_libro = r.quote_id.tiraje_principal or 0

    cuadernillo = fields.Integer('Cdrnllo pag', default=0,
                                  help='Páginas por cuadernillo. 0 = no se cose. '
                                       'x_coser = (Pag / Cdrnllo pag) × (tiraje + demasía).')
    x_coser = fields.Float('x coser', digits=(12, 2), compute='_compute_x_coser', store=True,
                            help='Total cuadernillos a coser = (Pag/Cdrnllo pag) × (tiraje+demasía).')
    tiraje = fields.Integer('Tiraje (millar)', compute='_compute_tiraje', store=True,
                             help='ceil(x_coser / 1000).')
    precio_unit = fields.Float('Precio Unitario', digits=(12, 2),
                                help='S/ por millar cosido.')
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.depends('pagina', 'cuadernillo', 'tiraje_libro', 'demasia')
    def _compute_x_coser(self):
        """Excel K76 = IF(I76=0, 0, C76/I76*(G76+F76))
          x_coser = (Pag / Cdrnllo_pag) × (tiraje + demasía_sección)
        """
        for r in self:
            if not r.cuadernillo:
                r.x_coser = 0
                continue
            n_cuadernillos_por_libro = (r.pagina or 0) / r.cuadernillo
            r.x_coser = n_cuadernillos_por_libro * ((r.tiraje_libro or 0) + (r.demasia or 0))

    @api.depends('x_coser')
    def _compute_tiraje(self):
        for r in self:
            r.tiraje = math.ceil(r.x_coser / 1000) if r.x_coser else 0

    @api.depends('tiraje', 'precio_unit')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = r.tiraje * r.precio_unit
