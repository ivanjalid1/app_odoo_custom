import math
from odoo import models, fields, api
from odoo.exceptions import UserError
from .tipos_seccion import get_caratula_codes


class ImprPrintQuote(models.Model):
    _name = 'impr.print.quote'
    _description = 'Presupuesto de Impresión'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name desc, id desc'

    # ── Cabecera ────────────────────────────────────────────────────────────
    name = fields.Char('Presupuesto', readonly=True, copy=False, default='New')
    client_id = fields.Many2one('res.partner', 'Cliente', tracking=True)
    nombre = fields.Char('Nombre')
    nota = fields.Text('Nota')
    date = fields.Date('Fecha', default=fields.Date.context_today)
    tc = fields.Float('Tipo de cambio', default=1.0, digits=(12, 2))
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviada'),
        ('approved', 'Aprobada'),
        ('production', 'En producción'),
        ('done', 'Terminada'),
        ('cancelled', 'Cancelada'),
    ], default='draft', tracking=True)
    sale_order_id = fields.Many2one('sale.order', 'Orden de Venta', readonly=True, copy=False)
    production_id = fields.Many2one('mrp.production', 'Orden de Producción', readonly=True, copy=False)

    # ── Especificaciones ────────────────────────────────────────────────────
    paginas_cara = fields.Integer('Páginas Cara', default=0)
    aprovechamiento = fields.Float('Aprovechamiento', digits=(12, 2))
    acabado = fields.Char('Acabado')
    clisse = fields.Float('Clissé', digits=(12, 2))

    # ── Formato / Cajas ─────────────────────────────────────────────────────
    ancho = fields.Float('Ancho', digits=(12, 2))
    largo = fields.Float('Largo', digits=(12, 2))
    peso_max_caja = fields.Float('Peso máx. caja', digits=(12, 2))
    libros_x_caja = fields.Integer('Libros x caja', default=0)
    peso_x_libro = fields.Float('Peso x libro', digits=(12, 2))
    peso_total = fields.Float('Peso total', digits=(12, 2), compute='_compute_peso_total', store=True)

    # ── Tirajes ─────────────────────────────────────────────────────────────
    tiraje_ids = fields.One2many('impr.quote.tiraje', 'quote_id', 'Tirajes adicionales',
                                  copy=True,
                                  help='Tirajes adicionales si el cliente pide varios. '
                                       'El principal está en el campo Tiraje directo.')
    tiraje_principal = fields.Integer('Tiraje', default=0,
                                       help='Cantidad de libros a imprimir (Excel K5).')
    # Páginas total = suma de páginas de interiores (Excel K4 = C9+C10+C11)
    # Editable para override manual
    paginas_total = fields.Integer('Páginas', default=0)

    # ── Páginas int / Interiores ─────────────────────────────────────────────
    paginas_int = fields.Selection(
        [(str(i), str(i)) for i in range(1, 11)],
        string='Páginas int', default='1'
    )
    interior_ids = fields.One2many('impr.quote.interior', 'quote_id', 'Interiores', copy=True)

    # ── Carátula ─────────────────────────────────────────────────────────────
    material_caratula_id = fields.Many2one('impr.paper.material', 'Material de la carátula')
    colores_caratula = fields.Char('Colores de la carátula')

    # ── Secciones de cálculo ─────────────────────────────────────────────────
    # copy=True en todos: Odoo 18 no copia One2many por defecto.
    papel_ids = fields.One2many('impr.quote.papel', 'quote_id', 'Papeles', copy=True)
    placa_ids = fields.One2many('impr.quote.placa', 'quote_id', 'Placas', copy=True)
    offset_ids = fields.One2many('impr.quote.offset', 'quote_id', 'Offset', copy=True)
    acabado_ids = fields.One2many('impr.quote.acabado', 'quote_id', 'Acabados Carátula', copy=True)
    doblado_ids = fields.One2many('impr.quote.doblado', 'quote_id', 'Doblado', copy=True)
    alce_ids = fields.One2many('impr.quote.alce', 'quote_id', 'Alce', copy=True)
    cosido_ids = fields.One2many('impr.quote.cosido', 'quote_id', 'Cosido', copy=True)
    encuadernado_ids = fields.One2many('impr.quote.encuadernado', 'quote_id', 'Encuadernado', copy=True)
    empaquetado_ids = fields.One2many('impr.quote.empaquetado', 'quote_id', 'Empaquetado', copy=True)
    troquelado_ids = fields.One2many('impr.quote.troquelado', 'quote_id', 'Troquelado', copy=True)
    corte_ids = fields.One2many('impr.quote.corte', 'quote_id', 'Cortes', copy=True)
    transporte_ids = fields.One2many('impr.quote.transporte', 'quote_id', 'Transporte', copy=True)

    # ── Totales ───────────────────────────────────────────────────────────────
    total_papeles = fields.Float('Total Papeles', compute='_compute_totales', store=True, digits=(12, 2))
    total_placas = fields.Float('Total Placas', compute='_compute_totales', store=True, digits=(12, 2))
    total_offset = fields.Float('Total Offset', compute='_compute_totales', store=True, digits=(12, 2))
    total_acabados = fields.Float('Total Acabados', compute='_compute_totales', store=True, digits=(12, 2))
    total_doblado = fields.Float('Total Doblado', compute='_compute_totales', store=True, digits=(12, 2))
    total_alce = fields.Float('Total Alce', compute='_compute_totales', store=True, digits=(12, 2))
    total_cosido = fields.Float('Total Cosido', compute='_compute_totales', store=True, digits=(12, 2))
    total_encuadernado = fields.Float('Total Encuadernado', compute='_compute_totales', store=True, digits=(12, 2))
    total_empaquetado = fields.Float('Total Empaquetado', compute='_compute_totales', store=True, digits=(12, 2))
    total_troquelado = fields.Float('Total Troquelado', compute='_compute_totales', store=True, digits=(12, 2))
    total_cortes = fields.Float('Total Cortes', compute='_compute_totales', store=True, digits=(12, 2))
    total_transporte = fields.Float('Total Transporte', compute='_compute_totales', store=True, digits=(12, 2))
    precio_total = fields.Float('Subtotal costos', compute='_compute_totales', store=True, digits=(12, 2))
    pct_papel = fields.Float('% de Papel', compute='_compute_totales', store=True, digits=(12, 2))
    pct_papel_placas = fields.Float('% de Papel + Placas', compute='_compute_totales', store=True, digits=(12, 2))
    pct_papel_placas_offs = fields.Float('% Papel Placas y Offs', compute='_compute_totales', store=True, digits=(12, 2))
    # ── Precio con IGV ────────────────────────────────────────────────────────
    precio_final_con_igv = fields.Float('Precio Final con IGV', compute='_compute_totales', store=True, digits=(12, 2))
    precio_unitario_con_igv = fields.Float('P. Unitario con IGV', compute='_compute_totales', store=True, digits=(12, 2))
    # ── Márgenes editables por cotización ────────────────────────────────────
    pct_ggff = fields.Float('GGFF %', default=7.5, digits=(5, 2),
                             help='Gastos generales (markup inclusivo). Defecto: 7.5% — el GGFF representa ese % del precio resultante.')
    pct_utilidad = fields.Float('Utilidad %', default=26.0, digits=(5, 2),
                                 help='Margen de utilidad (markup inclusivo). Defecto: 26%.')
    pct_comision = fields.Float('Comisión ventas %', default=2.0, digits=(5, 2),
                                 help='Comisión de ventas (markup inclusivo). Defecto: 2%.')
    # ── Precio final ──────────────────────────────────────────────────────────
    ggff = fields.Float('GGFF', compute='_compute_totales', store=True, digits=(12, 2))
    base_post_ggff = fields.Float('Total post GGFF', compute='_compute_totales', store=True, digits=(12, 2))
    utilidad = fields.Float('Utilidad', compute='_compute_totales', store=True, digits=(12, 2))
    base_post_utilidad = fields.Float('Total post Utilidad', compute='_compute_totales', store=True, digits=(12, 2))
    comision = fields.Float('Comisión ventas', compute='_compute_totales', store=True, digits=(12, 2))
    precio_final = fields.Float('Precio Final', compute='_compute_totales', store=True, digits=(12, 2))
    precio_unitario = fields.Float('Precio unitario', compute='_compute_totales', store=True, digits=(12, 2))
    # ── Detalle de fórmulas ───────────────────────────────────────────────────
    formula_breakdown = fields.Text('Detalle de fórmulas', compute='_compute_formula_breakdown', store=True)

    # ════════════════════════════════════════════════════════════════
    # HELPERS
    # ════════════════════════════════════════════════════════════════

    def _parse_colors(self, color_str):
        """'4/0' → (4.0, 0.0)  |  '1/1' → (1.0, 1.0)"""
        if not color_str:
            return 0.0, 0.0
        parts = color_str.strip().split('/')
        try:
            ct = float(parts[0]) if parts[0] else 0.0
            cr = float(parts[1]) if len(parts) > 1 and parts[1] else 0.0
            return ct, cr
        except (ValueError, IndexError):
            return 0.0, 0.0

    def _calc_imposicion(self, mat, book_ancho, book_largo):
        """Cuántos libros/carátulas entran por pliego máquina (imposición).

        Cada libro abierto ocupa: alto = book_largo, ancho_abierto = book_ancho × 2
        (el pliego se dobla a lo largo del eje de encuadernado).

        Se prueba la orientación que pone la dimensión MAYOR del pliego contra el
        alto del libro — que es la convención usada en las cotizaciones.
        """
        if not mat or not book_ancho or not book_largo:
            return 1
        d_mayor = max(mat.largo, mat.ancho)
        d_menor = min(mat.largo, mat.ancho)
        ancho_abierto = book_ancho * 2  # pliego abierto = 2 × ancho del libro
        imp = math.floor(d_mayor / book_largo) * math.floor(d_menor / ancho_abierto)
        return max(1, imp)

    def _calc_papel_vals(self, mat, tiraje, book_ancho, book_largo, paginas, demasia=0, tipo='interior'):
        """Devuelve los INPUTS para una línea de papel.
        Los campos calculados (pliegos, q_pliegos, subtotal, precio_unit, precio_resma,
        paquetes) son stored-computed en quote_papel y se recalculan automáticamente.
        Aprovechamiento (imposición) lo seteamos aquí como sugerencia inicial; el
        usuario puede sobreescribirlo — crítico para carátula (lomo+sangría).
        """
        if not mat:
            return {}
        imp = self._calc_imposicion(mat, book_ancho, book_largo)
        return {
            'material_id': mat.id,
            'paginas': paginas,
            'aprovechamiento': imp,
            'demasia': demasia,
            'precio_kg': mat.precio_kg,
        }

    # ════════════════════════════════════════════════════════════════
    # COMPUTES
    # ════════════════════════════════════════════════════════════════

    @api.onchange('tiraje_ids')
    def _onchange_tiraje_ids_sync(self):
        """Si el usuario llena la tabla de tirajes adicionales (legado),
        sincronizar tiraje_principal al primer valor."""
        if self.tiraje_ids and not self.tiraje_principal:
            self.tiraje_principal = self.tiraje_ids[0].tiraje or 0

    @api.depends('peso_x_libro', 'tiraje_principal')
    def _compute_peso_total(self):
        for q in self:
            q.peso_total = q.peso_x_libro * q.tiraje_principal

    @api.depends(
        'papel_ids.subtotal', 'placa_ids.subtotal', 'offset_ids.subtotal',
        'acabado_ids.subtotal', 'acabado_ids.aplica_a',
        'doblado_ids.subtotal', 'alce_ids.subtotal',
        'cosido_ids.subtotal', 'encuadernado_ids.subtotal', 'empaquetado_ids.subtotal',
        'troquelado_ids.subtotal', 'corte_ids.subtotal', 'transporte_ids.subtotal',
        'tiraje_principal', 'pct_ggff', 'pct_utilidad', 'pct_comision',
    )
    def _compute_totales(self):
        IGV = 1.18
        for q in self:
            tp  = sum(q.papel_ids.mapped('subtotal'))
            tpl = sum(q.placa_ids.mapped('subtotal'))
            tof = sum(q.offset_ids.mapped('subtotal'))
            tac = sum(q.acabado_ids.mapped('subtotal'))
            tdo = sum(q.doblado_ids.mapped('subtotal'))
            tal = sum(q.alce_ids.mapped('subtotal'))
            tco = sum(q.cosido_ids.mapped('subtotal'))
            ten = sum(q.encuadernado_ids.mapped('subtotal'))
            tem = sum(q.empaquetado_ids.mapped('subtotal'))
            tro = sum(q.troquelado_ids.mapped('subtotal'))
            tct = sum(q.corte_ids.mapped('subtotal'))
            ttr = sum(q.transporte_ids.mapped('subtotal'))
            total = tp + tpl + tof + tac + tdo + tal + tco + ten + tem + tro + tct + ttr

            q.total_papeles = tp
            q.total_placas = tpl
            q.total_offset = tof
            q.total_acabados = tac
            q.total_doblado = tdo
            q.total_alce = tal
            q.total_cosido = tco
            q.total_encuadernado = ten
            q.total_empaquetado = tem
            q.total_troquelado = tro
            q.total_cortes = tct
            q.total_transporte = ttr
            q.precio_total = total

            # ── Precio final — markup INCLUSIVO (fórmulas universales offset) ─
            # Cada tasa representa la proporción del margen en el precio resultante:
            #   precio_post_ggff = subtotal / (1 - tasa_ggff)   → ggff = precio_post_ggff * tasa_ggff
            #   precio_post_util = precio_post_ggff / (1 - tasa_util)
            #   precio_final     = precio_post_util / (1 - tasa_com)
            tasa_ggff = min(q.pct_ggff / 100.0, 0.9999)
            tasa_util = min(q.pct_utilidad / 100.0, 0.9999)
            tasa_com  = min(q.pct_comision / 100.0, 0.9999)

            base_post_ggff = total / (1.0 - tasa_ggff) if tasa_ggff else total
            ggff_val = base_post_ggff * tasa_ggff

            base_post_util = base_post_ggff / (1.0 - tasa_util) if tasa_util else base_post_ggff
            utilidad_val = base_post_util * tasa_util

            precio_final_val = base_post_util / (1.0 - tasa_com) if tasa_com else base_post_util
            comision_val = precio_final_val * tasa_com

            q.ggff = ggff_val
            q.base_post_ggff = base_post_ggff
            q.utilidad = utilidad_val
            q.base_post_utilidad = base_post_util
            q.comision = comision_val
            q.precio_final = precio_final_val
            q.precio_final_con_igv = precio_final_val * IGV
            q.precio_unitario = precio_final_val / q.tiraje_principal if q.tiraje_principal else 0
            q.precio_unitario_con_igv = q.precio_unitario * IGV

            # ── Porcentajes — base = precio_final (Excel). Fallback a total. ─
            base_pct = precio_final_val or total
            q.pct_papel             = (tp / base_pct * 100)            if base_pct else 0
            q.pct_papel_placas      = ((tp + tpl) / base_pct * 100)    if base_pct else 0
            q.pct_papel_placas_offs = ((tp + tpl + tof) / base_pct * 100) if base_pct else 0

    # ════════════════════════════════════════════════════════════════
    # FÓRMULAS — detalle de cálculo legible
    # ════════════════════════════════════════════════════════════════

    @api.depends(
        'papel_ids.subtotal', 'papel_ids.q_pliegos', 'papel_ids.precio_unit',
        'papel_ids.aprovechamiento', 'tc', 'ancho', 'largo',
        'tiraje_principal', 'precio_total', 'ggff', 'utilidad', 'comision',
        'precio_final', 'precio_unitario', 'precio_final_con_igv', 'precio_unitario_con_igv',
        'pct_ggff', 'pct_utilidad', 'pct_comision',
        'total_papeles', 'total_placas', 'total_offset', 'total_acabados',
        'total_doblado', 'total_alce', 'total_cosido',
        'total_troquelado', 'total_cortes', 'total_transporte',
        'total_encuadernado', 'total_empaquetado',
    )
    def _compute_formula_breakdown(self):
        caratula_codes = get_caratula_codes(self.env)
        for q in self:
            lines = [
                '═══ FÓRMULAS DE CÁLCULO (cotizador) ═══',
                '',
                f'  Formato libro : {q.largo} × {q.ancho} cm  (largo × ancho)',
                f'  Tiraje        : {q.tiraje_principal} unds',
                f'  Tipo de cambio: S/. {q.tc} / USD',
                '',
                '─── PAPELES ───',
            ]
            for papel in q.papel_ids:
                mat = papel.material_id
                if not mat:
                    continue
                # ── Calcular todo inline desde los datos crudos (no usar stored values) ──
                d1 = max(mat.largo, mat.ancho)
                d2 = min(mat.largo, mat.ancho)
                ancho_ab = q.ancho * 2
                fl1 = math.floor(d1 / (q.largo or 1))
                fl2 = math.floor(d2 / (ancho_ab or 1))
                imp = max(1, fl1 * fl2) if (fl1 * fl2) > 0 else 1
                kg_pl = (mat.largo * mat.ancho * mat.gramaje) / 10_000_000 if mat.gramaje else 0
                pk = papel.precio_kg or mat.precio_kg or 0
                tc = q.tc or 1.0
                precio_unit_calc = kg_pl * pk / 1.18 * tc if pk else 0
                demasia = papel.demasia or 0
                tiraje = q.tiraje_principal or 0

                es_car = papel.tipo in caratula_codes
                if es_car:
                    q_pliegos_calc = (tiraje + demasia) / imp
                    pliegos_calc = tiraje / imp
                else:
                    paginas = papel.paginas or 4
                    pxl = paginas / (4 * imp)
                    pliegos_calc = pxl * tiraje
                    q_pliegos_calc = pxl * (tiraje + demasia)

                subtotal_calc = q_pliegos_calc * precio_unit_calc

                label = papel.tipo.upper()
                if not es_car and papel.paginas:
                    label += f' ({papel.paginas} pág.)'
                lines += [
                    f'',
                    f'  [{label}] {mat.name}',
                    f'    Pliego   : {mat.largo} × {mat.ancho} cm | {mat.gramaje} g/m²',
                    f'    Imposic. : floor({d1}/{q.largo}) × floor({d2}/{ancho_ab:.1f}) = '
                    f'{fl1} × {fl2} = {imp} libros/pliego',
                ]
                if es_car:
                    lines.append(
                        f'    Q pliegos: (tiraje+dem)÷imp = ({tiraje}+{demasia:.0f})÷'
                        f'{imp} = {q_pliegos_calc:.1f}'
                    )
                else:
                    paginas = papel.paginas or 4
                    pxl = paginas / (4 * imp)
                    lines.append(f'    Pliegos/libro: {paginas}÷(4×{imp}) = {pxl:.2f}')
                    lines.append(
                        f'    Q pliegos: {pxl:.2f} × ({tiraje}+{demasia:.0f}) = {q_pliegos_calc:.1f}'
                    )
                lines += [
                    f'    Kg/pliego: {mat.largo}×{mat.ancho}×{mat.gramaje}÷10,000,000 = {kg_pl:.6f} kg',
                    f'    Precio   : {kg_pl:.6f} × {pk:.4f} ÷ 1.18 × {tc} = S/. {precio_unit_calc:.4f}/pliego',
                    f'    Subtotal : {q_pliegos_calc:.1f} × {precio_unit_calc:.4f} = S/. {subtotal_calc:,.2f}',
                ]
            lines += [
                '',
                '─── RESUMEN DE COSTOS ───',
                '',
                f'  Papel               : S/. {q.total_papeles:>12,.2f}',
                f'  Placas              : S/. {q.total_placas:>12,.2f}',
                f'  Offset              : S/. {q.total_offset:>12,.2f}',
                f'  Acabados carátula   : S/. {q.total_acabados:>12,.2f}',
                f'  Doblado             : S/. {q.total_doblado:>12,.2f}',
                f'  Alce                : S/. {q.total_alce:>12,.2f}',
                f'  Cosido              : S/. {q.total_cosido:>12,.2f}',
                f'  Troquelado          : S/. {q.total_troquelado:>12,.2f}',
                f'  Encuadernado        : S/. {q.total_encuadernado:>12,.2f}',
                f'  Cortes              : S/. {q.total_cortes:>12,.2f}',
                f'  Empaquetado         : S/. {q.total_empaquetado:>12,.2f}',
                f'  Transporte          : S/. {q.total_transporte:>12,.2f}',
                f'  {"─"*34}',
                '',
                '─── PRECIO FINAL ───',
                '',
                f'  Subtotal costos     : S/. {q.precio_total:>12,.2f}',
                f'  + GGFF {q.pct_ggff:.1f}% (incl.)    : S/. {q.ggff:>12,.2f}',
                f'  + Utilidad {q.pct_utilidad:.1f}% (incl.): S/. {q.utilidad:>12,.2f}',
                f'  + Comisión {q.pct_comision:.1f}% (incl.) : S/. {q.comision:>12,.2f}',
                f'  {"─"*34}',
                f'  PRECIO FINAL s/IGV  : S/. {q.precio_final:>12,.2f}',
                f'  PRECIO FINAL c/IGV  : S/. {q.precio_final_con_igv:>12,.2f}',
                f'  P. UNITARIO s/IGV   : S/. {q.precio_unitario:>12,.4f}',
                f'  P. UNITARIO c/IGV   : S/. {q.precio_unitario_con_igv:>12,.4f}',
            ]
            q.formula_breakdown = '\n'.join(lines)

    # ════════════════════════════════════════════════════════════════
    # AUTO-POPULATE
    # ════════════════════════════════════════════════════════════════

    @api.onchange(
        'material_caratula_id', 'colores_caratula',
        'interior_ids',
        'tiraje_ids', 'tiraje_principal',
        'ancho', 'largo',
        'paginas_cara',
        'tc',
        'peso_x_libro', 'peso_max_caja',
    )
    def _onchange_auto_populate(self):
        """Helpers de cálculo auto (peso_x_libro, libros_x_caja, peso_total)."""
        self._auto_peso_x_libro()
        self._auto_libros_x_caja()
        self.peso_total = (self.peso_x_libro or 0.0) * (
            self.tiraje_principal or (self.tiraje_ids[0].tiraje if self.tiraje_ids else 0)
        )

    @api.onchange('papel_ids')
    def _on_papel_change(self):
        """Recalcular campos derivados. Filas hijas se crean en papel.create()."""
        caratula_codes = get_caratula_codes(self.env)
        self.paginas_total = sum(p.paginas for p in self.papel_ids if p.tipo and p.tipo not in caratula_codes)
        self._auto_peso_x_libro()
        self._auto_libros_x_caja()
        self.peso_total = (self.peso_x_libro or 0.0) * (self.tiraje_principal or 0)

    def _auto_peso_x_libro(self):
        """Calcula peso_x_libro desde papel_ids (Excel B108, revisión 2026-04-26).
          peso = (ancho×largo/10000) × Σ_secciones(g_m2) / 1000 [kg]
          - Carátula : g_m2 = gramaje × 2 × pag_caratula  (cubre forro + lomo + sangría)
          - Interior : g_m2 = pag/2 × gramaje
        """
        if not self.ancho or not self.largo:
            return
        caratula_codes = get_caratula_codes(self.env)
        area_m2 = (self.ancho * self.largo) / 10000.0
        total_g_m2 = 0.0
        for p in self.papel_ids:
            if p.tipo in caratula_codes:
                total_g_m2 += (p.peso or 0) * 2 * (p.paginas or 0)
            else:
                total_g_m2 += (p.paginas or 0) / 2.0 * (p.peso or 0)
        self.peso_x_libro = area_m2 * total_g_m2 / 1000.0

    def _auto_libros_x_caja(self):
        """libros_x_caja = floor(peso_max_caja / peso_x_libro). (Excel H102)"""
        if self.peso_max_caja and self.peso_x_libro:
            self.libros_x_caja = int(self.peso_max_caja / self.peso_x_libro)

    def _populate_acabados(self):
        """Crea las 5 líneas estándar de acabado de carátula (Excel rows 44-48).
        q_pliegos y tiraje se leen del offset carátula (Excel J44=J32, M44=M32).
        """
        caratula_codes = get_caratula_codes(self.env)
        offset_car = next((o for o in self.offset_ids if o.tipo in caratula_codes), None)
        q_pliegos = offset_car.q_pliegos if offset_car else 0
        tiraje_millar = offset_car.tiraje if offset_car else 0
        default_codes = ['PLAST_BRILLO', 'BARNIZ_UV_MATE', 'REPUJADO',
                         'PLAST_MATE', 'BARNIZ_BRILLO']
        services = self.env['impr.finishing.service'].search(
            [('code', 'in', default_codes), ('categoria', '=', 'acabado')]
        )
        by_code = {s.code: s for s in services}
        new_lines = []
        for i, code in enumerate(default_codes, start=1):
            svc = by_code.get(code)
            vals = {
                'factor': 1.0,
                'q_pliegos': q_pliegos,
                'tiraje': tiraje_millar,
                'clisse': 0,
                'precio_unit': 0,
                'sequence': i * 10,
                'aplica_a': 'caratula',
            }
            if svc:
                vals['service_id'] = svc.id
                if svc.price_type == 'unit':
                    vals['clisse'] = svc.price or 0.0
                else:
                    vals['precio_unit'] = svc.price or 0.0
            new_lines.append((0, 0, vals))
        self.acabado_ids = [(5, 0, 0)] + new_lines

    def _secciones(self):
        """
        Devuelve lista de dicts con la info de cada sección (carátula + interiores).
        """
        tiraje = self.tiraje_principal or (self.tiraje_ids[0].tiraje if self.tiraje_ids else 0)
        secs = []
        # Carátula
        if self.material_caratula_id:
            ct, cr = self._parse_colors(self.colores_caratula)
            secs.append({
                'tipo': 'caratula',
                'label': 'Carátula',
                'mat': self.material_caratula_id,
                'paginas': self.paginas_cara,
                'color_t': ct,
                'color_r': cr,
                'tiraje': tiraje,
                'seq': 1,
            })
        # Interiores
        for idx, interior in enumerate(self.interior_ids, start=2):
            if interior.material_id:
                ct, cr = self._parse_colors(interior.colores)
                secs.append({
                    'tipo': 'interior',
                    'label': interior.name or f'Interior {idx-1}',
                    'mat': interior.material_id,
                    'paginas': interior.paginas or 0,
                    'color_t': ct,
                    'color_r': cr,
                    'tiraje': tiraje,
                    'seq': idx * 10,
                    'interior_id': interior._origin.id if interior._origin else False,
                })
        return secs

    def _populate_papel(self):
        book_ancho = self.ancho
        book_largo = self.largo
        tiraje = self.tiraje_principal or (self.tiraje_ids[0].tiraje if self.tiraje_ids else 0)
        caratula_codes = get_caratula_codes(self.env)

        # Conservar líneas existentes que el usuario editó (por tipo)
        existing = {l.tipo: l for l in self.papel_ids if l.tipo in caratula_codes}
        # Para interiores puede haber múltiples — indexamos por interior_id
        existing_int = {l.interior_id.id: l for l in self.papel_ids if l.tipo and l.tipo not in caratula_codes and l.interior_id}

        new_lines = []
        for sec in self._secciones():
            vals = self._calc_papel_vals(
                sec['mat'], tiraje, book_ancho, book_largo,
                sec['paginas'], tipo=sec['tipo'],
            )
            if not vals:
                continue
            vals.update({'tipo': sec['tipo'], 'sequence': sec['seq']})
            if sec['tipo'] not in caratula_codes and sec.get('interior_id'):
                vals['interior_id'] = sec['interior_id']
            new_lines.append((0, 0, vals))

        self.papel_ids = [(5, 0, 0)] + new_lines  # (5) = borrar todos, luego crear

    def _pliegos_per_book(self, tipo, paginas, imp):
        """Pliegos por libro:
        - Carátula: 1/imp (una carátula cada `imp` libros)
        - Interior: paginas / (4*imp)   (1 pliego doblado = 4 páginas × `imp` libros)
        """
        if not imp:
            return 0.0
        if tipo in get_caratula_codes(self.env):
            return 1.0 / imp
        return (paginas or 4) / (4.0 * imp)

    def _populate_placas(self):
        """Fórmula:
          - Solo tiro (cr=0): placas = ceil(pliegos_libro / maqui) × color_t
          - Tiro+retiro:       placas = (pliegos_libro / maqui) × (color_t + color_r)
        Maqui típico: carátula=0.5, interior=0.5.
        """
        book_ancho = self.ancho
        book_largo = self.largo
        new_lines = []
        for sec in self._secciones():
            imp = self._calc_imposicion(sec['mat'], book_ancho, book_largo)
            pliegos_libro = self._pliegos_per_book(sec['tipo'], sec['paginas'], imp)
            maqui = 0.5  # default para placas (tanto carátula como interior)
            new_lines.append((0, 0, {
                'tipo': sec['tipo'],
                'material_id': sec['mat'].id,
                'pagina': sec['paginas'],
                'aprovechamiento': imp,
                'pliegos': pliegos_libro,
                'maqui': maqui,
                'color_t': sec['color_t'],
                'color_r': sec['color_r'],
                'precio_unit': 0,
                'sequence': sec['seq'],
            }))
        self.placa_ids = [(5, 0, 0)] + new_lines

    def _populate_offset(self):
        """Fórmula:
          q_pliegos = (tiraje + demasia) × (pliegos_libro / maqui) × factor
          tiraje_millar = ceil(q_pliegos / 1000)
          subtotal = tiraje_millar × precio_unit   (precio por millar)
        Maqui: carátula=1 (pliego completo), interior=0.5 (media máquina).
        """
        book_ancho = self.ancho
        book_largo = self.largo
        caratula_codes = get_caratula_codes(self.env)
        # Demasia por sección (de papel_ids si ya existe; sino 0)
        demasia_by_seq = {p.sequence: (p.demasia or 0) for p in self.papel_ids}
        new_lines = []
        for sec in self._secciones():
            imp = self._calc_imposicion(sec['mat'], book_ancho, book_largo)
            pliegos_libro = self._pliegos_per_book(sec['tipo'], sec['paginas'], imp)
            demasia = demasia_by_seq.get(sec['seq'], 0)
            # NOTA: maqui, color_t, color_r se computan automáticamente desde PLACAS
            # (ver quote_offset._compute_from_placa). No los seteamos aquí.
            new_lines.append((0, 0, {
                'tipo': sec['tipo'],
                'material_id': sec['mat'].id,
                'pagina': sec['paginas'],
                'aprovechamiento': imp,
                'pliegos': pliegos_libro,
                'demasia': demasia,
                'factor': 1.0,
                'precio_unit': 0,
                'sequence': sec['seq'],
            }))
        self.offset_ids = [(5, 0, 0)] + new_lines

    def _populate_doblado(self):
        """Fórmula:
          x_doblar = q_pliegos_offset × factor_doblado
          tiraje_millar = ceil(x_doblar / 1000)
          subtotal = tiraje_millar × precio_unit
        Factor por defecto: carátula=0 (no se dobla), interior=1 (32-pág signatures).
        """
        # Q pliegos por sección (viene del offset, que ya fue populado antes)
        q_by_seq = {o.sequence: (o.q_pliegos or 0) for o in self.offset_ids}
        caratula_codes = get_caratula_codes(self.env)
        new_lines = []
        for sec in self._secciones():
            factor = 0.0 if sec['tipo'] in caratula_codes else 1.0
            new_lines.append((0, 0, {
                'tipo': sec['tipo'],
                'material_id': sec['mat'].id,
                'factor': factor,
                'q_pliegos': q_by_seq.get(sec['seq'], 0),
                'precio_unit': 0,
                'sequence': sec['seq'],
            }))
        self.doblado_ids = [(5, 0, 0)] + new_lines

    def _populate_alce(self):
        """Fórmula:
          x_alzar = x_doblar × factor_alce (1.5)
          tiraje_millar = ceil(x_alzar / 1000)
          subtotal = tiraje_millar × precio_unit
        Factor por defecto: carátula=0, interior=1.5.
        """
        x_doblar_by_seq = {d.sequence: (d.x_doblar or 0) for d in self.doblado_ids}
        caratula_codes = get_caratula_codes(self.env)
        new_lines = []
        for sec in self._secciones():
            factor = 0.0 if sec['tipo'] in caratula_codes else 1.5
            new_lines.append((0, 0, {
                'tipo': sec['tipo'],
                'material_id': sec['mat'].id,
                'factor': factor,
                'q_pliegos': x_doblar_by_seq.get(sec['seq'], 0),  # = x_doblar input
                'precio_unit': 0,
                'sequence': sec['seq'],
            }))
        self.alce_ids = [(5, 0, 0)] + new_lines

    def _populate_cosido(self):
        """Fórmula (Excel K76):
          x_coser = (Pag / Cdrnllo_pag) × (tiraje + demasía_sección)
          tiraje_millar = ceil(x_coser / 1000)
          subtotal = tiraje_millar × precio_unit
        Pag, demasía y tiraje se toman automáticamente del papel/cabecera.
        Solo aplica a interiores. Cdrnllo_pag = 0 por defecto (usuario lo define).
        """
        caratula_codes = get_caratula_codes(self.env)
        new_lines = []
        for sec in self._secciones():
            if sec['tipo'] in caratula_codes:
                continue
            new_lines.append((0, 0, {
                'sequence': sec['seq'],
                'cuadernillo': 0,
                'precio_unit': 0,
            }))
        self.cosido_ids = [(5, 0, 0)] + new_lines

    def _populate_encuadernado(self):
        """Crea líneas base de encuadernado con cantidad=1 (usuario ingresa precio).
        cantidad=1 porque cada tipo es un trabajo completo; subtotal = 1 × precio_unit.
        Si no aplica, el usuario deja precio_unit=0.
        """
        tipos = ['Remachado con Liga', 'Forrado Capitel y Sepa', 'Engrapado']
        new_lines = []
        for i, tipo in enumerate(tipos, start=1):
            new_lines.append((0, 0, {
                'tipo': tipo,
                'cantidad': 1,      # 1 trabajo = 1 ejecución por OP
                'precio_unit': 0,
                'sequence': i * 10,
            }))
        self.encuadernado_ids = [(5, 0, 0)] + new_lines

    def _populate_empaquetado(self):
        """Crea líneas de empaquetado calculando cajas según tiraje y libros/caja."""
        tiraje = self.tiraje_principal or (self.tiraje_ids[0].tiraje if self.tiraje_ids else 0)
        libros_x_caja = self.libros_x_caja or 0
        peso_total = self.peso_total or 0
        peso_x_libro = self.peso_x_libro or 0
        n_cajas = math.ceil(tiraje / libros_x_caja) if libros_x_caja and tiraje else 0
        tiraje_millar = math.ceil(tiraje / 1000) if tiraje else 0
        new_lines = [
            (0, 0, {
                'tipo': 'sellado_libro',
                'peso_x_libro': peso_x_libro,
                'peso_total': peso_total,
                'cantidad': tiraje_millar,
                'precio_unit': 0,
                'sequence': 10,
            }),
            (0, 0, {
                'tipo': 'caja',
                'peso_x_libro': peso_x_libro,
                'peso_total': peso_total,
                'cantidad': n_cajas,
                'precio_unit': 0,
                'sequence': 20,
            }),
            (0, 0, {
                'tipo': 'sellado_caja',
                'peso_x_libro': peso_x_libro,
                'peso_total': peso_total,
                'cantidad': n_cajas,
                'precio_unit': 0,
                'sequence': 30,
            }),
        ]
        self.empaquetado_ids = [(5, 0, 0)] + new_lines

    def _populate_troquelado(self):
        """Crea una línea de troquelado por sección de papel.
        Fórmula nueva (Excel M87 = ROUNDUP(K*J/1000)): Factor × Q Pliegos / 1000.
        Default factor=0 (no se troquela). Usuario lo activa donde aplica.
        """
        new_lines = []
        for sec in self._secciones():
            new_lines.append((0, 0, {
                'sequence': sec['seq'],
                'factor': 0.0,  # default: no troquelar; usuario activa
                'precio_unit': 0,
                'c_fijo': 0,
            }))
        self.troquelado_ids = [(5, 0, 0)] + new_lines

    def _populate_cortes(self):
        """Crea líneas de corte inicial y final.

        Inicial: cantidad = Σ(q_pliegos_i / unidad_paquete_i) de papel_ids
                 (= resmas totales que pasan por la guillotina, incluyendo demasía)
        Final:   cantidad = ceil(tiraje / 1000) millares de libros
        """
        tiraje = self.tiraje_principal or (self.tiraje_ids[0].tiraje if self.tiraje_ids else 0)
        # Corte Inicial: usar los q_pliegos ya calculados en papel_ids
        # (_populate_papel se ejecuta antes en _onchange_auto_populate)
        resmas_total = 0.0
        for papel in self.papel_ids:
            mat = papel.material_id
            if mat and papel.q_pliegos:
                hojas_paq = mat.unidad_paquete or 500
                resmas_total += papel.q_pliegos / hojas_paq

        tiraje_millar = math.ceil(tiraje / 1000) if tiraje else 1
        new_lines = [
            (0, 0, {
                'tipo': 'inicial',
                'cantidad': resmas_total,
                'precio_unit': 0,
                'sequence': 10,
            }),
            (0, 0, {
                'tipo': 'final',
                'cantidad': tiraje_millar,
                'precio_unit': 0,
                'sequence': 20,
            }),
        ]
        self.corte_ids = [(5, 0, 0)] + new_lines

    # ════════════════════════════════════════════════════════════════
    # SIMULACIÓN DE PRECIO — para tirajes alternativos
    # ════════════════════════════════════════════════════════════════

    def _simulate_precio(self, tiraje_alt, pct_utilidad_alt):
        """Recalcula el precio final (sin IGV) para un tiraje/utilidad
        alternativos, reutilizando los precios unitarios y estructura actual
        de la cotización. Fijos (placas, troquelado, encuadernado, C Fijo de
        acabados) se mantienen fijos; el resto escala con tiraje+demasía.

        La demasía es siempre per-material: cada papel conserva su propia
        demasía absoluta configurada en el cuadro de Papeles. El alt solo
        varía el tiraje (y opcionalmente el margen de utilidad).
        """
        self.ensure_one()
        if not tiraje_alt:
            return 0.0

        tiraje_millar = math.ceil(tiraje_alt / 1000) if tiraje_alt else 0

        def eff_demasia(papel):
            return papel.demasia or 0

        # Índices por sequence para lookup rápido
        papel_by_seq = {p.sequence: p for p in self.papel_ids}
        offset_by_seq = {o.sequence: o for o in self.offset_ids}
        doblado_by_seq = {d.sequence: d for d in self.doblado_ids}

        # 1. Papel: q_pliegos = pliegos_por_libro × (tiraje + demasía_efectiva)
        papel_total = 0.0
        for p in self.papel_ids:
            q_pliegos = (p.pliegos or 0) * (tiraje_alt + eff_demasia(p))
            papel_total += q_pliegos * (p.precio_unit or 0)

        # 2. Placas: fijo (depende de pliegos_por_libro, no de tiraje)
        placa_total = sum(self.placa_ids.mapped('subtotal'))

        # 3. Offset: q_pliegos_off = papel.pliegos × (tiraje+dem) / maqui × factor
        offset_total = 0.0
        off_q_pliegos = {}
        for o in self.offset_ids:
            papel = papel_by_seq.get(o.sequence)
            if not papel or not o.maqui:
                off_q_pliegos[o.sequence] = 0
                continue
            q_pliegos = (papel.pliegos or 0) * (tiraje_alt + eff_demasia(papel)) / o.maqui
            off_q_pliegos[o.sequence] = q_pliegos
            tm = math.ceil(q_pliegos / 1000) if q_pliegos else 0
            offset_total += tm * (o.precio_unit or 0)

        # 4. Acabados de carátula: tiraje_millar + clisse fijo
        acabado_total = 0.0
        for a in self.acabado_ids:
            if a.aplica_a == 'ninguno':
                continue
            # q_pliegos del acabado = q_pliegos del offset de la misma sección
            # (aplica_a: caratula → tomar offset carátula, interior → interior)
            off_match = self.offset_ids.filtered(lambda o, ap=a.aplica_a: o.tipo == ap)[:1]
            q_pliegos_ac = off_q_pliegos.get(off_match.sequence, 0) if off_match else 0
            tm_ac = math.ceil(q_pliegos_ac / 1000) if q_pliegos_ac else 0
            acabado_total += tm_ac * (a.precio_unit or 0) + (a.clisse or 0)

        # 5. Doblado: x_doblar = q_pliegos_offset × factor_doblado
        doblado_total = 0.0
        x_doblar_by_seq = {}
        for d in self.doblado_ids:
            q_pliegos = off_q_pliegos.get(d.sequence, 0)
            x_doblar = q_pliegos * (d.factor or 0)
            x_doblar_by_seq[d.sequence] = x_doblar
            tm = math.ceil(x_doblar / 1000) if x_doblar else 0
            doblado_total += tm * (d.precio_unit or 0)

        # 6. Alce: x_alzar = x_doblar × factor_alce
        alce_total = 0.0
        for a in self.alce_ids:
            x_doblar = x_doblar_by_seq.get(a.sequence, 0)
            x_alzar = x_doblar * (a.factor or 0)
            tm = math.ceil(x_alzar / 1000) if x_alzar else 0
            alce_total += tm * (a.precio_unit or 0)

        # 7. Cosido: x_coser = (Pag / Cdrnllo_pag) × (tiraje + demasía_sección)
        cosido_total = 0.0
        for c in self.cosido_ids:
            if not c.cuadernillo:
                continue
            papel = papel_by_seq.get(c.sequence)
            if not papel:
                continue
            n_cuadernillos = (papel.paginas or 0) / c.cuadernillo
            x_coser = n_cuadernillos * (tiraje_alt + eff_demasia(papel))
            tm = math.ceil(x_coser / 1000) if x_coser else 0
            cosido_total += tm * (c.precio_unit or 0)

        # 8. Troquelado: factor × q_pliegos_off / 1000 + c_fijo (por sección)
        troquelado_total = 0.0
        for t in self.troquelado_ids:
            q_p = off_q_pliegos.get(t.sequence, 0)
            v = (t.factor or 0) * q_p
            tm = math.ceil(v / 1000) if v else 0
            troquelado_total += tm * (t.precio_unit or 0) + (t.c_fijo or 0)
        # Encuadernado: fijo
        encuadernado_total = sum(self.encuadernado_ids.mapped('subtotal'))

        # 9. Cortes
        corte_total = 0.0
        resmas_total = 0.0
        for p in self.papel_ids:
            mat = p.material_id
            if not mat:
                continue
            hojas_paq = mat.unidad_paquete or 500
            q_pliegos = (p.pliegos or 0) * (tiraje_alt + eff_demasia(p))
            resmas_total += q_pliegos / hojas_paq if hojas_paq else 0
        for c in self.corte_ids:
            if c.tipo == 'inicial':
                corte_total += resmas_total * (c.precio_unit or 0)
            elif c.tipo == 'final':
                corte_total += tiraje_millar * (c.precio_unit or 0)

        # 10. Empaquetado
        empaquetado_total = 0.0
        for e in self.empaquetado_ids:
            if e.tipo == 'sellado_libro':
                empaquetado_total += tiraje_millar * (e.precio_unit or 0)
            elif e.tipo == 'caja':
                lxc = e.libros_x_caja or 0
                n_cajas = math.ceil(tiraje_alt / lxc) if lxc else 0
                empaquetado_total += n_cajas * (e.precio_unit or 0)
            elif e.tipo == 'sellado_caja':
                caja = self.empaquetado_ids.filtered(lambda ee: ee.tipo == 'caja')[:1]
                lxc = (caja.libros_x_caja or 0) if caja else 0
                n_cajas = math.ceil(tiraje_alt / lxc) if lxc else 0
                empaquetado_total += n_cajas * (e.precio_unit or 0)

        # 11. Transporte: escala con peso (peso × tiraje_alt)
        peso_alt = (self.peso_x_libro or 0) * tiraje_alt
        cant_flete = self._flete_minimo(peso_alt) if peso_alt else 0
        transporte_total = 0.0
        for t in self.transporte_ids:
            transporte_total += cant_flete * (t.precio_unit or 0)

        subtotal = (papel_total + placa_total + offset_total + acabado_total
                    + doblado_total + alce_total + cosido_total
                    + troquelado_total + encuadernado_total
                    + corte_total + empaquetado_total + transporte_total)

        # GGFF / Utilidad alternativa / Comisión — markup inclusivo
        tasa_ggff = min((self.pct_ggff or 0) / 100.0, 0.9999)
        tasa_util = min((pct_utilidad_alt or 0) / 100.0, 0.9999)
        tasa_com = min((self.pct_comision or 0) / 100.0, 0.9999)

        base_post_ggff = subtotal / (1.0 - tasa_ggff) if tasa_ggff else subtotal
        base_post_util = base_post_ggff / (1.0 - tasa_util) if tasa_util else base_post_ggff
        precio_final = base_post_util / (1.0 - tasa_com) if tasa_com else base_post_util
        return precio_final

    @staticmethod
    def _flete_minimo(peso_total_kg):
        """Tabla de flete mínimo (Excel M107)."""
        if peso_total_kg < 2000:
            return 400
        if peso_total_kg < 5000:
            return 600
        if peso_total_kg < 7000:
            return 1000
        if peso_total_kg < 10000:
            return 1200
        if peso_total_kg < 12000:
            return 1700
        return peso_total_kg  # cargas muy pesadas: cobrar peso real

    def _populate_transporte(self):
        """Crea 1 línea de transporte usando la tabla de flete mínimo."""
        peso_total = self.peso_total or 0
        cantidad_flete = self._flete_minimo(peso_total) if peso_total else 0
        self.transporte_ids = [(5, 0, 0), (0, 0, {
            'tipo': 'Transporte',
            'peso_total': peso_total,
            'cantidad': cantidad_flete,
            'precio_unit': 0,
            'sequence': 10,
        })]

    # ════════════════════════════════════════════════════════════════
    # PÁGINAS INT → INTERIORES
    # ════════════════════════════════════════════════════════════════

    @api.onchange('paginas_int')
    def _onchange_paginas_int(self):
        n = int(self.paginas_int or '1')
        existing = len(self.interior_ids)
        if n > existing:
            for i in range(existing + 1, n + 1):
                self.interior_ids = [(0, 0, {'name': f'Interior {i}', 'sequence': i * 10})]
        elif n < existing:
            to_remove = self.interior_ids[n:]
            self.interior_ids = [(2, r.id, 0) for r in to_remove if r.id]

    # ════════════════════════════════════════════════════════════════
    # CRUD
    # ════════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('impr.print.quote') or 'New'
        records = super().create(vals_list)
        # En modo copia Odoo ya trae los hijos del origen; no agregues defaults.
        if self.env.context.get('impr_copying_quote'):
            return records
        hot_melt = self.env['impr.finishing.service'].search(
            [('code', '=', 'HOTMELT')], limit=1)
        for rec in records:
            if not rec.interior_ids:
                self.env['impr.quote.interior'].create({
                    'quote_id': rec.id,
                    'name': 'Interior 1',
                    'sequence': 10,
                })
            # Defaults frecuentes — el usuario casi siempre los va a tener.
            # Troquelado: ya no se crea aquí (default 1 fila fija) — ahora se crea
            # una línea por papel vía cascada en quote_papel.create().
            if not rec.encuadernado_ids:
                tiraje = rec.tiraje_principal or 0
                enc_vals = {
                    'quote_id': rec.id,
                    'tipo': 'Hot Melt',
                    'cantidad': math.ceil(tiraje / 1000) if tiraje else 0,
                    'sequence': 10,
                }
                if hot_melt:
                    enc_vals['service_id'] = hot_melt.id
                    if hot_melt.price:
                        enc_vals['precio_unit'] = hot_melt.price
                self.env['impr.quote.encuadernado'].create(enc_vals)
            if not rec.corte_ids:
                self.env['impr.quote.corte'].create([
                    {'quote_id': rec.id, 'tipo': 'inicial', 'sequence': 10},
                    {'quote_id': rec.id, 'tipo': 'final', 'sequence': 20},
                ])
        return records

    def copy(self, default=None):
        """Duplicación completa: copia cabecera + TODAS las secciones (papeles,
        placas, offset, acabados, etc.). Activa un flag de contexto para que los
        hijos de papel no se auto-generen (Odoo ya copia placa/offset/doblado/alce/
        cosido desde el origen). Sin el flag, tendríamos duplicados por la
        cascada en papel.create()."""
        self.ensure_one()
        default = dict(default or {})
        default.setdefault('name', 'New')
        default.setdefault('state', 'draft')
        default.setdefault('sale_order_id', False)
        default.setdefault('production_id', False)
        default.setdefault('date', fields.Date.context_today(self))
        new = super(ImprPrintQuote, self.with_context(impr_copying_quote=True)).copy(default)
        # Recalcular campos derivados de onchange (no están marcados como compute)
        new._auto_peso_x_libro()
        new._auto_libros_x_caja()
        return new

    def write(self, vals):
        res = super().write(vals)
        if 'papel_ids' in vals:
            caratula_codes = get_caratula_codes(self.env)
            for q in self:
                q._auto_peso_x_libro()
                q._auto_libros_x_caja()
                q.paginas_total = sum(p.paginas for p in q.papel_ids if p.tipo and p.tipo not in caratula_codes)
            self._sync_children_from_papel()
        return res

    def _sync_children_from_papel(self):
        """Crea filas faltantes en placa/offset/doblado/alce/cosido para cada papel.
        NO borra ni modifica filas existentes — solo agrega las que faltan."""
        caratula_codes = get_caratula_codes(self.env)
        for q in self:
            existing = {
                'placa': set(q.placa_ids.mapped('sequence')),
                'offset': set(q.offset_ids.mapped('sequence')),
                'doblado': set(q.doblado_ids.mapped('sequence')),
                'alce': set(q.alce_ids.mapped('sequence')),
                'cosido': set(q.cosido_ids.mapped('sequence')),
            }
            for p in q.papel_ids:
                seq = p.sequence
                tipo = p.tipo or 'interior'
                es_car = tipo in caratula_codes
                if seq not in existing['placa']:
                    self.env['impr.quote.placa'].create({
                        'quote_id': q.id, 'sequence': seq, 'maqui': 0.5,
                    })
                if seq not in existing['offset']:
                    # maqui se computa desde PLACAS automáticamente
                    self.env['impr.quote.offset'].create({
                        'quote_id': q.id, 'sequence': seq,
                        'demasia': p.demasia or 0,
                    })
                if seq not in existing['doblado']:
                    self.env['impr.quote.doblado'].create({
                        'quote_id': q.id, 'sequence': seq,
                        'factor': 0 if es_car else 1.0,
                    })
                if seq not in existing['alce']:
                    self.env['impr.quote.alce'].create({
                        'quote_id': q.id, 'sequence': seq,
                        'factor': 0 if es_car else 1.5,
                    })
                if not es_car and seq not in existing['cosido']:
                    self.env['impr.quote.cosido'].create({
                        'quote_id': q.id, 'sequence': seq,
                    })

    # ════════════════════════════════════════════════════════════════
    # BOTONES
    # ════════════════════════════════════════════════════════════════

    def action_actualizar_secciones(self):
        """Recalcula todo lo que depende del tiraje, materiales y pesos, y
        recarga el formulario. Pisa cantidades en encuadernado/empaquetado/
        cortes/transporte — el usuario puede volver a editar después."""
        self.ensure_one()
        self._refresh_dependent_on_tiraje()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'impr.print.quote',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _refresh_dependent_on_tiraje(self):
        """Sincroniza líneas hijas con el estado actual de cabecera (tiraje, pesos).
        Llamado por el botón 'Actualizar secciones'. Pisa cantidades existentes."""
        self.ensure_one()
        # 1. Recalcular pesos derivados (peso_x_libro, libros_x_caja)
        self._auto_peso_x_libro()
        self._auto_libros_x_caja()
        peso_total = (self.peso_x_libro or 0) * (self.tiraje_principal or 0)
        # peso_total es compute=stored, depende de peso_x_libro y tiraje_principal,
        # así que se recalcula solo. Lo leemos para empaquetado/transporte abajo.

        tiraje = self.tiraje_principal or (
            self.tiraje_ids[0].tiraje if self.tiraje_ids else 0)
        tiraje_millar = math.ceil(tiraje / 1000) if tiraje else 0

        # 2. Encuadernado: cantidad = tiraje en millares (cobro per millar)
        for enc in self.encuadernado_ids:
            enc.cantidad = tiraje_millar

        # 3. Empaquetado (Excel rows 107-109): solo Caja tiene pesos.
        peso_max = self.peso_max_caja or 12
        pxl = self.peso_x_libro or 0
        libros_x_caja = int(peso_max / pxl) if pxl else 0
        n_cajas = math.ceil(tiraje / libros_x_caja) if libros_x_caja and tiraje else 0
        for emp in self.empaquetado_ids:
            if emp.tipo == 'sellado_libro':
                emp.peso_x_libro = 0
                emp.peso_total = 0
                emp.peso_max_caja = 0
                emp.libros_x_caja = 0
                emp.cantidad = tiraje_millar
            elif emp.tipo == 'caja':
                emp.peso_x_libro = pxl
                emp.peso_total = peso_total
                emp.peso_max_caja = peso_max
                emp.libros_x_caja = libros_x_caja
                emp.cantidad = n_cajas
            elif emp.tipo == 'sellado_caja':
                emp.peso_x_libro = 0
                emp.peso_total = 0
                emp.peso_max_caja = 0
                emp.libros_x_caja = 0
                emp.cantidad = n_cajas

        # 4. Cortes (inicial/final): ya se autocomputan vía @depends en quote_corte.

        # 5. Transporte: peso_total y cantidad (flete por tabla)
        cant_flete = self._flete_minimo(peso_total) if peso_total else 0
        for t in self.transporte_ids:
            t.peso_total = peso_total
            t.cantidad = cant_flete

    def action_duplicar_papel(self):
        """Duplica la última línea de Papeles. Las filas hijas se crean automáticamente en papel.create()."""
        self.ensure_one()
        last = self.papel_ids.sorted('sequence', reverse=True)[:1]
        if not last:
            return
        self.env['impr.quote.papel'].create({
            'quote_id': self.id,
            'tipo': last.tipo,
            'material_id': last.material_id.id if last.material_id else False,
            'paginas': last.paginas,
            'aprovechamiento': last.aprovechamiento,
            'demasia': last.demasia,
            'precio_kg': last.precio_kg,
        })

    def action_send(self):
        self.state = 'sent'
        return False

    def action_approve(self):
        self.state = 'approved'
        return False

    def action_cancel(self):
        self.state = 'cancelled'
        return False

    def action_draft(self):
        self.state = 'draft'
        return False

    def action_liberar(self):
        self.ensure_one()
        if self.state != 'approved':
            raise UserError('Solo se puede liberar una cotización aprobada.')

        # Producto servicio "Trabajo de Impresión"
        product_tmpl = self.env.ref('imprenta_quoter.product_trabajo_impresion', raise_if_not_found=False)
        if product_tmpl:
            product = product_tmpl.product_variant_id
        else:
            product = self.env['product.product'].search([('name', '=', 'Trabajo de Impresión')], limit=1)
        if not product:
            product = self.env['product.product'].search([('type', '=', 'service')], limit=1)

        # ── Crear Sale Order ──────────────────────────────────────────────
        # price_unit = precio UNITARIO (por libro), qty = tiraje → total = qty × price
        # NO usar precio_final como price_unit porque Odoo multiplicaría por tiraje y
        # daría precio × tiraje^2 (bug: si tiraje=1000 y precio_final=15974, el SO
        # daría S/ 15,974,000 en vez de S/ 15,974).
        tiraje = self.tiraje_principal or 1
        so_line_vals = {
            'name': self.nombre or self.name,
            'product_uom_qty': tiraje,
            'price_unit': self.precio_unitario or (self.precio_final / tiraje if tiraje else 0),
        }
        if product:
            so_line_vals['product_id'] = product.id

        so = self.env['sale.order'].create({
            'partner_id': self.client_id.id,
            'origin': self.name,
            'order_line': [(0, 0, so_line_vals)],
        })
        self.sale_order_id = so.id

        # ── Materiales crudos desde papel_ids (con UoM correcta) ─────────
        raw_moves = []
        for papel in self.papel_ids:
            mat = papel.material_id
            if not mat or not mat.product_id or not papel.q_pliegos:
                continue
            product_mat = mat.product_id
            # Usar UoM del material si está configurada, sino la del producto
            uom = mat.uom_id or product_mat.uom_id
            raw_moves.append((0, 0, {
                'product_id': product_mat.id,
                'product_uom_qty': papel.q_pliegos,
                'product_uom': uom.id,
                'name': mat.name,
            }))

        # ── Crear Manufacturing Order ─────────────────────────────────────
        mo_product = product or self.env['product.product'].search([], limit=1)
        mo_vals = {
            'origin': self.name,
            'product_qty': self.tiraje_principal or 1,
            'impr_quote_id': self.id,
            'date_start': fields.Datetime.now(),
        }
        if mo_product:
            mo_vals['product_id'] = mo_product.id
        if raw_moves:
            mo_vals['move_raw_ids'] = raw_moves

        mo = self.env['mrp.production'].create(mo_vals)
        self.production_id = mo.id

        # ── Auto-crear procesos del Gantt desde secciones de la cotización ─
        self._create_processes_from_quote(mo)

        self.state = 'production'

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.production',
            'res_id': mo.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_processes_from_quote(self, mo):
        """Auto-crea impr.production.process vinculados a la OP
        basándose en las secciones con datos de la cotización.
        """
        ProcessTemplate = self.env['impr.process.template']
        WorkCenter = self.env['mrp.workcenter']
        Process = self.env['impr.production.process']

        def tmpl(code):
            return ProcessTemplate.search([('code', '=', code)], limit=1)

        def wc(code):
            return WorkCenter.search([('code', '=', code)], limit=1)

        # Costos por proceso, tomados de la cotización.
        # GUILL_INI y GUILL_FIN se reparten el total_cortes según tipo inicial/final.
        total_inicial = sum(c.subtotal for c in self.corte_ids if c.tipo == 'inicial')
        total_final   = sum(c.subtotal for c in self.corte_ids if c.tipo == 'final')
        # Papel + placas van al corte inicial (primer uso del material).
        cost_gnl_ini = self.total_papeles + self.total_placas + total_inicial

        def add(code, wc_code, name_fallback, duration=1, people=1, delay=0, cost=0.0):
            t = tmpl(code)
            w = wc(wc_code)
            Process.create({
                'production_id': mo.id,
                'process_template_id': t.id if t else False,
                'name': t.name if t else name_fallback,
                'workcenter_id': w.id if w else False,
                'sequence': seq[0],
                'duration_days': duration,
                'people_required': people,
                'delay_days': delay,
                'state': 'pending',
                'cost_total': cost,
            })
            seq[0] += 10

        seq = [10]  # mutable para modificar dentro de add()

        # 1. Corte inicial — siempre si hay papel (incluye costo papeles + placas + corte inicial)
        if self.papel_ids:
            add('GUILL_INI', 'GUILL', 'Guillotina — Corte inicial',
                duration=1, people=1, cost=cost_gnl_ini)

        # 2. Impresión Offset — si hay líneas de offset con trabajo
        if any(o.q_pliegos > 0 for o in self.offset_ids):
            # Estimar duración: ~1 día por cada 5000 pliegos
            total_pliegos = sum(o.q_pliegos for o in self.offset_ids)
            duration = max(1, math.ceil(total_pliegos / 5000))
            add('OFFSET', 'OFFSET', 'Impresión Offset',
                duration=duration, people=2, cost=self.total_offset)

        # 3. Doblado
        if any(d.q_pliegos > 0 for d in self.doblado_ids):
            add('DOBLA', 'DOBLA', 'Doblado',
                duration=1, people=1, cost=self.total_doblado)

        # 4. Alce / Encartado
        if any(a.q_pliegos > 0 for a in self.alce_ids):
            add('ALCE', 'ENCAR', 'Encartado / Alce',
                duration=1, people=2, cost=self.total_alce)

        # 5. Cosido
        if any(c.pliegos > 0 for c in self.cosido_ids):
            add('COSIDO', 'COSER', 'Cosido',
                duration=1, people=1, cost=self.total_cosido)

        # 6. Acabados carátula (barniz, plastificado, etc.) — incluye troquelado
        if any(a.subtotal > 0 for a in self.acabado_ids):
            add('BARNIZ_UV', 'ACAB', 'Acabados Carátula',
                duration=1, people=1,
                cost=self.total_acabados + self.total_troquelado)

        # 7. Encuadernado — detectar si es tercero (Hot Melt, Wire-O, etc.)
        if any(e.subtotal > 0 for e in self.encuadernado_ids):
            # Si el tipo contiene palabras que indican tercero, agregar proceso TERCERO
            tipos_encuad = [e.tipo.lower() for e in self.encuadernado_ids if e.tipo]
            es_tercero = any(
                k in t for t in tipos_encuad
                for k in ('tercero', 'wire', 'tapa dura', 'hot stamp')
            )
            if es_tercero:
                add('TERCERO', '', 'Servicios de Terceros',
                    duration=3, people=1, delay=1, cost=self.total_encuadernado)
            else:
                add('HOTMELT', 'ACAB', 'Encuadernado / Hot Melt',
                    duration=1, people=1, cost=self.total_encuadernado)

        # 8. Corte final — siempre
        add('GUILL_FIN', 'GUILL', 'Corte Final',
            duration=1, people=1, cost=total_final)

        # 9. Empaque y despacho — empaquetado + transporte
        tiraje = self.tiraje_principal or 0
        dur_despacho = max(1, math.ceil(tiraje / 2000))
        add('DESPACHO', 'ACAB', 'Empaque y Despacho',
            duration=dur_despacho, people=2,
            cost=self.total_empaquetado + self.total_transporte)
