import math
from odoo import models, fields, api
from .tipos_seccion import get_caratula_codes


class ImprQuotePapel(models.Model):
    _name = 'impr.quote.papel'
    _description = 'Línea de papel en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    # tipo_id: Many2one con autocomplete (como material_id).
    # tipo (Char): se sincroniza desde tipo_id.code. La lógica interna usa tipo (string).
    tipo_id = fields.Many2one(
        'impr.section.type',
        string='Tipo',
        default=lambda self: self.env['impr.section.type'].search(
            [('code', '=', 'interior')], limit=1
        ),
        domain=[('active', '=', True)],
        help='Tipo de sección (editable desde Configuración → Tipos de Sección).',
    )
    tipo = fields.Char(
        string='Código tipo',
        compute='_compute_tipo_from_id',
        inverse='_inverse_tipo_to_id',
        store=True,
    )

    @api.depends('tipo_id')
    def _compute_tipo_from_id(self):
        for r in self:
            r.tipo = r.tipo_id.code if r.tipo_id else False

    def _inverse_tipo_to_id(self):
        for r in self:
            if r.tipo and (not r.tipo_id or r.tipo_id.code != r.tipo):
                st = self.env['impr.section.type'].search(
                    [('code', '=', r.tipo)], limit=1
                )
                r.tipo_id = st.id if st else False

    interior_id = fields.Many2one('impr.quote.interior', 'Interior ref.')
    material_id = fields.Many2one('impr.paper.material', 'Material')
    paginas = fields.Integer('Páginas', default=0)
    demasia = fields.Float('Demasía', digits=(12, 2))
    precio_kg = fields.Float('$kg', digits=(12, 4))

    # ── Campos sincronizados del material ────────────────────────────────────
    largo = fields.Float('Largo', digits=(12, 2),
                         compute='_compute_from_material', store=True)
    ancho = fields.Float('Ancho', digits=(12, 2),
                         compute='_compute_from_material', store=True)
    peso = fields.Float('Peso (g/m²)', digits=(12, 2),
                        compute='_compute_from_material', store=True)

    @api.depends('material_id', 'material_id.largo', 'material_id.ancho', 'material_id.gramaje')
    def _compute_from_material(self):
        for r in self:
            mat = r.material_id
            r.largo = mat.largo if mat else 0
            r.ancho = mat.ancho if mat else 0
            r.peso = mat.gramaje if mat else 0

    # ── aprovechamiento — editable por el usuario ────────────────────────────
    # Se inicia automáticamente (onchange material/tipo), pero el usuario puede
    # sobreescribirlo (crítico para carátula donde depende del lomo/sangría).
    aprovechamiento = fields.Float(
        'Aprovecha...', digits=(12, 2), default=0,
        help='Libros o carátulas que entran en un pliego (imposición). '
             'Auto para interior; MANUAL para carátula (lomo+sangría afectan).',
    )

    @api.onchange('material_id', 'tipo')
    def _onchange_material_suggest_aprov(self):
        """Al cambiar material o tipo, sugiere Rendim (convención Excel) y precio_kg.
          Excel Rendim:
            Interior : pages per pliego (both sides) = 4 × imp
            Carátula : = imp (usuario ajusta por lomo/sangría)
        """
        if not self.material_id or not self.quote_id:
            return
        q = self.quote_id
        mat = self.material_id
        if mat.precio_kg:
            self.precio_kg = mat.precio_kg
        if self.aprovechamiento:
            return
        if not q.largo or not q.ancho:
            return
        d_mayor = max(mat.largo, mat.ancho)
        d_menor = min(mat.largo, mat.ancho)
        ancho_ab = q.ancho * 2
        imp = (math.floor(d_mayor / q.largo) * math.floor(d_menor / ancho_ab)
               if (q.largo and ancho_ab) else 0)
        imp = max(1, imp) if imp > 0 else 1
        # Interior: Rendim = 4 × imp (Excel row 9 D9=32 para BOOK CREAM 102x63 + libro 15x23)
        # Carátula: Rendim = imp (ej. 8); el usuario frecuentemente lo baja a 4 por lomo
        if self.tipo in get_caratula_codes(self.env):
            self.aprovechamiento = imp
        else:
            self.aprovechamiento = 4 * imp

    # ── Campos calculados ─────────────────────────────────────────────────────
    pliegos = fields.Float('Pliegos', digits=(12, 4), compute='_compute_calcs', store=True,
                           help='Pliegos por libro (rendim = paginas / pliegos para interior).')
    q_pliegos = fields.Float('Q Pliegos', digits=(12, 2), compute='_compute_calcs', store=True,
                             help='Pliegos totales: pliegos × (tiraje + demasía).')
    precio_resma = fields.Float('$ Resma', digits=(12, 6), compute='_compute_calcs', store=True)
    paquetes = fields.Float('Paquetes', digits=(12, 2), compute='_compute_calcs', store=True)
    precio_unit = fields.Float('Precio Unit.', digits=(12, 6), compute='_compute_calcs', store=True)
    subtotal = fields.Float('Subtotal', digits=(12, 2), compute='_compute_calcs', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Asigna sequence único + crea filas hijas en placa/offset/doblado/alce/cosido.
        Si se está duplicando una cotización (context['impr_copying_quote']),
        salta la auto-cascada: Odoo ya copia los hijos desde el origen."""
        assigned = {}
        for vals in vals_list:
            if not vals.get('sequence') or vals.get('sequence') == 10:
                qid = vals.get('quote_id')
                if qid:
                    if qid not in assigned:
                        existing = self.search([('quote_id', '=', qid)], order='sequence desc', limit=1)
                        assigned[qid] = existing.sequence if existing else 0
                    assigned[qid] += 10
                    vals['sequence'] = assigned[qid]
        records = super().create(vals_list)
        if self.env.context.get('impr_copying_quote'):
            return records
        caratula_codes = get_caratula_codes(self.env)
        for rec in records:
            if not rec.quote_id:
                continue
            seq = rec.sequence
            tipo = rec.tipo or 'interior'
            qid = rec.quote_id.id
            # Verificar que no existan ya (evitar duplicados)
            if not self.env['impr.quote.placa'].search_count([('quote_id', '=', qid), ('sequence', '=', seq)]):
                self.env['impr.quote.placa'].create({'quote_id': qid, 'sequence': seq, 'maqui': 0.5})
            es_caratula = tipo in caratula_codes
            if not self.env['impr.quote.offset'].search_count([('quote_id', '=', qid), ('sequence', '=', seq)]):
                # maqui se computa desde PLACAS
                self.env['impr.quote.offset'].create({
                    'quote_id': qid, 'sequence': seq,
                })
            if not self.env['impr.quote.doblado'].search_count([('quote_id', '=', qid), ('sequence', '=', seq)]):
                self.env['impr.quote.doblado'].create({
                    'quote_id': qid, 'sequence': seq,
                    'factor': 0 if es_caratula else 1.0,
                })
            if not self.env['impr.quote.alce'].search_count([('quote_id', '=', qid), ('sequence', '=', seq)]):
                self.env['impr.quote.alce'].create({
                    'quote_id': qid, 'sequence': seq,
                    'factor': 0 if es_caratula else 1.5,
                })
            if not es_caratula and not self.env['impr.quote.cosido'].search_count([('quote_id', '=', qid), ('sequence', '=', seq)]):
                self.env['impr.quote.cosido'].create({'quote_id': qid, 'sequence': seq})
            # Troquelado: una línea por sección con factor=0 por defecto
            if not self.env['impr.quote.troquelado'].search_count([('quote_id', '=', qid), ('sequence', '=', seq)]):
                self.env['impr.quote.troquelado'].create({
                    'quote_id': qid, 'sequence': seq, 'factor': 0.0,
                })
        return records

    def unlink(self):
        """Cascade: al borrar una fila de Papel, borrar las filas correspondientes
        (por quote_id + sequence) en placas/offset/doblado/alce/cosido/troquelado."""
        sections_to_clean = [
            ('impr.quote.placa',     'placa_ids'),
            ('impr.quote.offset',    'offset_ids'),
            ('impr.quote.doblado',   'doblado_ids'),
            ('impr.quote.alce',      'alce_ids'),
            ('impr.quote.cosido',    'cosido_ids'),
            ('impr.quote.troquelado', 'troquelado_ids'),
        ]
        keys = [(p.quote_id.id, p.sequence) for p in self if p.quote_id]
        res = super().unlink()
        for model, _ in sections_to_clean:
            for qid, seq in keys:
                orphans = self.env[model].search([('quote_id', '=', qid), ('sequence', '=', seq)])
                if orphans:
                    orphans.unlink()
        return res

    @api.depends(
        'material_id', 'material_id.largo', 'material_id.ancho',
        'material_id.gramaje', 'material_id.precio_kg', 'material_id.unidad_paquete',
        'quote_id.tc', 'quote_id.tiraje_principal',
        'paginas', 'demasia', 'tipo', 'precio_kg', 'aprovechamiento',
    )
    def _compute_calcs(self):
        for r in self:
            mat = r.material_id
            q = r.quote_id

            if not mat or not r.aprovechamiento:
                r.pliegos = 0
                r.q_pliegos = 0
                r.precio_resma = 0
                r.paquetes = 0
                r.precio_unit = 0
                r.subtotal = 0
                continue

            tc = q.tc or 1.0
            tiraje = q.tiraje_principal or 0
            demasia = r.demasia or 0
            imp = r.aprovechamiento

            # ── Pliegos por libro (Excel E8/E9: pliegos = pag / rendim) ─────
            pliegos_full = r.paginas / imp if imp else 0
            r.pliegos = pliegos_full  # se guarda redondeado a 2 dec para display

            # ── Q pliegos totales: usa precisión COMPLETA (no el redondeado) ──
            r.q_pliegos = pliegos_full * (tiraje + demasia)

            # ── Precio (fórmulas EXACTAS del Excel row 8) ────────────────────
            hojas_paquete = mat.unidad_paquete or 500
            pk = r.precio_kg or mat.precio_kg or 0

            # $ Resma (Excel L8) = precio resma USD con IGV del catálogo
            #   Papel estándar: = largo × ancho × gramaje × $kg × paquetes / 10.000.000
            #   Cartón (paquete=1): el catálogo guarda $/unidad directo (Excel W27=U27),
            #     no pasa por la fórmula de kg×área. Detectamos por unidad_paquete<=1.
            if hojas_paquete and hojas_paquete > 1:
                r.precio_resma = (mat.largo * mat.ancho * (mat.gramaje or 0)
                                  * pk * hojas_paquete) / 10_000_000
            else:
                r.precio_resma = pk  # $/unidad ya es precio final USD inc IGV

            # Paquetes (Excel M8) = unidad_paquete (hojas por paquete, catálogo V)
            r.paquetes = hojas_paquete

            # P Unit (Excel N8) = $Resma × TC / 1.18 / paquetes
            r.precio_unit = (r.precio_resma * tc / 1.18 / hojas_paquete
                             if hojas_paquete else 0)

            # P Total (Excel O8) = P Unit × Q Pliegos
            r.subtotal = r.q_pliegos * r.precio_unit
