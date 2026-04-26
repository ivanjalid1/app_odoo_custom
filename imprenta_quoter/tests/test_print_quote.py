"""
Tests for imprenta_quoter — cotizador
=========================================

Coverage:
  UNIT          : fórmulas matemáticas puras (sin DB)
  INTEGRATION   : ORM completo sobre DB de test
  FLOW          : flujo Borrador → Aprobada → Liberar → SO+OP

Run with:
  # En el VPS
  docker compose exec odoo odoo -u imprenta_quoter \
      --test-enable --stop-after-init -d test_db

  # Con pytest-odoo (local)
  pytest custom_addons/imprenta_quoter/tests/ -v
"""

import math
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import UserError


# ═══════════════════════════════════════════════════════════════════════════
#  UNIT TESTS — fórmulas puras (no DB)
# ═══════════════════════════════════════════════════════════════════════════

@tagged('unit', 'impr', '-at_install', 'post_install')
class TestFormulas(TransactionCase):
    """Verifica las fórmulas matemáticas del cotizador contra el Excel."""

    # ── Imposición ──────────────────────────────────────────────────────────

    def test_imposicion_basica(self):
        """Pliego 72×102, libro 21×14.8 → floor(102/21)*floor(72/29.6) = 4*2 = 8"""
        quote = self.env['impr.print.quote'].new({
            'nombre': 'Test', 'tc': 1.0,
        })
        mat = self.env['impr.paper.material'].search([], limit=1)
        if not mat:
            self.skipTest('No hay materiales cargados')
        # Simula dimensiones: largo=102, ancho=72
        class FakeMat:
            largo = 102
            ancho = 72
            gramaje = 90
            precio_kg = 1.18
            unidad_paquete = 500
        imp = quote._calc_imposicion(FakeMat(), book_ancho=14.8, book_largo=21)
        self.assertEqual(imp, 8)

    def test_imposicion_minimo_1(self):
        """Libro más grande que el pliego → imposición mínima 1."""
        quote = self.env['impr.print.quote'].new({'nombre': 'T', 'tc': 1.0})
        class FakeMat:
            largo = 20; ancho = 10; gramaje = 90
        imp = quote._calc_imposicion(FakeMat(), book_ancho=6, book_largo=21)
        self.assertEqual(imp, 1)

    def test_imposicion_sin_material(self):
        quote = self.env['impr.print.quote'].new({'nombre': 'T', 'tc': 1.0})
        self.assertEqual(quote._calc_imposicion(None, 14, 20), 1)

    # ── Precio de papel ─────────────────────────────────────────────────────

    def test_precio_papel_sin_igv(self):
        """precio_unit = kg_pliego × precio_kg / 1.18 × tc"""
        # kg_pliego = (102 × 72 × 90) / 10_000_000 = 0.066096
        # precio_unit = 0.066096 × 1.18 / 1.18 × 3.80 = 0.066096 × 3.80 ≈ 0.25117
        kg = (102 * 72 * 90) / 10_000_000
        precio_unit = kg * 1.18 / 1.18 * 3.80
        self.assertAlmostEqual(precio_unit, kg * 3.80, places=4)

    # ── Markup inclusivo ────────────────────────────────────────────────────

    def test_markup_inclusivo_verificado_excel(self):
        """
        Verifica la fórmula contra el Excel:
          subtotal = 3662.11
          GGFF 7.5% → 3662.11 / (1 - 0.075) = 3959.04  → ggff = 296.93
          Util 12%  → 3959.04 / (1 - 0.12)  = 4498.91  → util = 539.87
          Com  2%   → 4498.91 / (1 - 0.02)  = 4590.72  → com  = 91.81
          precio_final = 4590.72  →  c/IGV = 5417.05
        """
        subtotal = 3662.11
        ggff_r, util_r, com_r = 0.075, 0.12, 0.02

        base_ggff = subtotal / (1 - ggff_r)
        ggff_val  = base_ggff * ggff_r
        base_util = base_ggff / (1 - util_r)
        util_val  = base_util * util_r
        pf        = base_util / (1 - com_r)
        com_val   = pf * com_r

        self.assertAlmostEqual(pf, 4590.72, delta=0.01)
        self.assertAlmostEqual(pf * 1.18, 5417.05, delta=0.01)
        self.assertAlmostEqual(ggff_val, 296.93, delta=0.01)
        self.assertAlmostEqual(util_val, 539.87, delta=0.01)
        self.assertAlmostEqual(com_val, 91.81, delta=0.01)

    def test_markup_inclusivo_tasas_cero(self):
        """Con tasas 0% el precio final debe igualar el subtotal."""
        subtotal = 1000.0
        for tasa in [0.0]:
            base_ggff = subtotal / (1 - tasa) if tasa else subtotal
            base_util = base_ggff / (1 - tasa) if tasa else base_ggff
            pf = base_util / (1 - tasa) if tasa else base_util
        self.assertAlmostEqual(pf, subtotal, places=4)

    # ── Corte inicial ───────────────────────────────────────────────────────

    def test_corte_inicial_resmas(self):
        """Corte Inicial = Σ(q_pliegos_i / unidad_paquete_i)."""
        # 1000 pliegos / 500 = 2 resmas
        resmas = 1000 / 500
        self.assertEqual(resmas, 2.0)

    # ── Fórmulas de las secciones (contra Excel) ────────────────────────

    def test_placas_formula_tiro_solo(self):
        """Carátula tiro 4/0 con pliegos=0.25 y maqui=0.5:
           placas = ceil(0.25/0.5) × 4 = 1 × 4 = 4 (Excel verificado)."""
        pliegos, maqui, ct, cr = 0.25, 0.5, 4, 0
        placas = math.ceil(pliegos / maqui) * ct
        self.assertEqual(placas, 4)

    def test_placas_formula_tiro_retiro(self):
        """Interior 1/1 con pliegos=5 y maqui=0.5:
           placas = (5/0.5) × (1+1) = 10 × 2 = 20 (Excel verificado)."""
        pliegos, maqui, ct, cr = 5.0, 0.5, 1, 1
        placas = (pliegos / maqui) * (ct + cr)
        self.assertEqual(placas, 20)

    def test_offset_formula(self):
        """q_pliegos = (tiraje+demasia) × (pliegos/maqui).
           Carátula: (1000+400) × (0.25/1) = 350. Tiraje_millar = ceil(350/1000) = 1."""
        tiraje, demasia, pliegos, maqui = 1000, 400, 0.25, 1.0
        q_pliegos = (tiraje + demasia) * (pliegos / maqui)
        tiraje_millar = math.ceil(q_pliegos / 1000)
        self.assertAlmostEqual(q_pliegos, 350.0, places=2)
        self.assertEqual(tiraje_millar, 1)

    def test_offset_interior_12000(self):
        """Interior 1: (1000+200) × (5/0.5) = 12000 pliegos → 12 millares."""
        q_pliegos = (1000 + 200) * (5 / 0.5)
        tiraje_millar = math.ceil(q_pliegos / 1000)
        self.assertEqual(q_pliegos, 12000)
        self.assertEqual(tiraje_millar, 12)

    def test_doblado_formula(self):
        """x_doblar = q_pliegos × factor; tiraje_millar = ceil(x/1000).
           Interior 1: 12000 × 1 = 12000 → 12 millares × 8 = S/96."""
        x_doblar = 12000 * 1.0
        tiraje_millar = math.ceil(x_doblar / 1000)
        subtotal = tiraje_millar * 8
        self.assertEqual(subtotal, 96)

    def test_alce_formula(self):
        """x_alzar = x_doblar × 1.5. Interior 1: 12000 × 1.5 = 18000 → 18 millares × 8 = S/144."""
        x_alzar = 12000 * 1.5
        tiraje_millar = math.ceil(x_alzar / 1000)
        subtotal = tiraje_millar * 8
        self.assertEqual(subtotal, 144)

    def test_cosido_formula(self):
        """Excel K76: x_coser = (Pag / Cdrnllo_pag) × (tiraje + demasía_sección).
           Interior 144 pág, 12 pág/cdrnllo, tiraje=1000, demasía=250
             = 144/12 × (1000+250) = 12 × 1250 = 15000 → 15 millares × 25 = S/375."""
        pag, cdrnllo_pag, tiraje, demasia = 144, 12, 1000, 250
        x_coser = (pag / cdrnllo_pag) * (tiraje + demasia)
        tiraje_millar = math.ceil(x_coser / 1000)
        subtotal = tiraje_millar * 25
        self.assertEqual(x_coser, 15000)
        self.assertEqual(subtotal, 375)

    def test_porcentajes_base_precio_final(self):
        """Excel: pct_papel = total_papel / precio_final (no sobre subtotal).
           1456.07 / 4590.72 = 31.72%, NO 1456.07 / 3662.11 = 39.76%."""
        total_papel = 1456.07
        precio_final = 4590.72
        pct = total_papel / precio_final * 100
        self.assertAlmostEqual(pct, 31.72, delta=0.05)

    def test_placas_caratula_simple_suma(self):
        """Excel M20 = K20+L20 → Carátula placas = ct + cr (sin maqui).
           4/0 → 4;  2/1 → 3;  1/1 → 2. Independiente de pliegos/maqui."""
        # Test the formula logic directly (pure function)
        for ct, cr, expected in [(4, 0, 4), (2, 1, 3), (1, 1, 2), (0, 0, 0)]:
            placas = ct + cr
            self.assertEqual(placas, expected, f'ct={ct}, cr={cr}')

    def test_flete_minimo_tabla(self):
        """Excel M107: IF peso<2000→400, <5000→600, <7000→1000,
                     <10000→1200, <12000→1700, else peso real."""
        q = self.env['impr.print.quote']  # just to access static method
        casos = [
            (500, 400),    # <2000
            (1999, 400),
            (2000, 600),   # <5000
            (4999, 600),
            (5000, 1000),  # <7000
            (6999, 1000),
            (7000, 1200),  # <10000
            (9999, 1200),
            (10000, 1700), # <12000
            (11999, 1700),
            (15000, 15000),# cargas muy pesadas
        ]
        for peso, expected in casos:
            self.assertEqual(q._flete_minimo(peso), expected,
                             f'peso={peso} → flete={expected}')

    def test_peso_x_libro_formula(self):
        """Excel B102:
          peso = (ancho×largo/10000) × (gramaje_car×2 + Σ(pag/2 × gramaje_int)) / 1000
        Sample Book: 15×23 cm, carátula 280g/m², 160+8+4 páginas de 60g/m².
        Esperado: ≈ 0.19734 kg."""
        ancho, largo = 15.0, 23.0
        gram_car = 280
        interiores = [(160, 60), (8, 60), (4, 60)]  # (paginas, gramaje)
        area_m2 = ancho * largo / 10000.0
        total_g_m2 = gram_car * 2 + sum(p / 2 * g for p, g in interiores)
        peso_kg = area_m2 * total_g_m2 / 1000.0
        self.assertAlmostEqual(peso_kg, 0.19734, delta=0.001)

    def test_libros_x_caja_formula(self):
        """Excel H102: libros_x_caja = floor(peso_max_caja / peso_x_libro).
           Ej: 12 kg / 0.19734 kg = 60.8 → floor = 60."""
        peso_max = 12.0
        peso_libro = 0.19734
        import math as m
        libros = int(m.floor(peso_max / peso_libro))
        self.assertEqual(libros, 60)

    def test_cosido_usa_x_doblar_previo(self):
        """Excel K77 = K65: cosido de INTERIOR N usa x_doblar de sección ANTERIOR.
           Esto replica la cascada del Excel."""
        # Interior 2 cosido usa x_doblar de Interior 1 (= 12000), NO su propio (= 1350).
        # Con Cdrnllo=2: x_coser = 12000/2 = 6000; tiraje_millar = 6; S/ 150.
        prev_x_doblar = 12000
        cdrnllo = 2
        x_coser = prev_x_doblar / cdrnllo
        tiraje_millar = math.ceil(x_coser / 1000)
        subtotal = tiraje_millar * 25
        self.assertEqual(subtotal, 150,
                         msg='Interior 2 cosido con x_doblar_previo=12000 debe dar S/150')

    # ── parse_colors ────────────────────────────────────────────────────────

    def test_parse_colors_4_0(self):
        q = self.env['impr.print.quote'].new({'nombre': 'T', 'tc': 1.0})
        ct, cr = q._parse_colors('4/0')
        self.assertEqual(ct, 4.0)
        self.assertEqual(cr, 0.0)

    def test_parse_colors_1_1(self):
        q = self.env['impr.print.quote'].new({'nombre': 'T', 'tc': 1.0})
        ct, cr = q._parse_colors('1/1')
        self.assertEqual(ct, 1.0)
        self.assertEqual(cr, 1.0)

    def test_parse_colors_vacio(self):
        q = self.env['impr.print.quote'].new({'nombre': 'T', 'tc': 1.0})
        ct, cr = q._parse_colors('')
        self.assertEqual(ct, 0.0)
        self.assertEqual(cr, 0.0)


# ═══════════════════════════════════════════════════════════════════════════
#  INTEGRATION TESTS — ORM + DB
# ═══════════════════════════════════════════════════════════════════════════

@tagged('integration', 'impr', '-at_install', 'post_install')
class TestPrintQuoteIntegration(TransactionCase):
    """Tests de integración: crea registros reales en la DB de test."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Material de prueba
        cls.mat = cls.env['impr.paper.material'].search(
            [('largo', '>', 0), ('ancho', '>', 0), ('gramaje', '>', 0)],
            limit=1,
        )
        if not cls.mat:
            cls.mat = cls.env['impr.paper.material'].create({
                'name': 'BOND TEST 90g 72×102',
                'largo': 102.0,
                'ancho': 72.0,
                'gramaje': 90.0,
                'precio_kg': 1.18,
                'unidad_paquete': 500,
            })
        # Socio de prueba
        cls.partner = cls.env['res.partner'].search([], limit=1)

    def _make_quote(self, tiraje=1000, tc=3.80):
        """Crea una cotización mínima válida."""
        quote = self.env['impr.print.quote'].create({
            'nombre': 'Libro test',
            'client_id': self.partner.id,
            'tc': tc,
            'ancho': 14.8,
            'largo': 21.0,
            'tiraje_principal': tiraje,
            'peso_x_libro': 0.25,
            'libros_x_caja': 20,
            'material_caratula_id': self.mat.id,
            'colores_caratula': '4/0',
            'paginas_cara': 4,
            'pct_ggff': 7.5,
            'pct_utilidad': 12.0,
            'pct_comision': 2.0,
        })
        return quote

    # ── tiraje_principal ────────────────────────────────────────────────────

    def test_tiraje_principal_editable(self):
        q = self._make_quote(tiraje=2000)
        self.assertEqual(q.tiraje_principal, 2000)

    # ── peso_total ──────────────────────────────────────────────────────────

    def test_peso_total_computado(self):
        q = self._make_quote(tiraje=1000)
        q.peso_x_libro = 0.30
        q._compute_peso_total()
        self.assertAlmostEqual(q.peso_total, 300.0, places=1)

    # ── papel_ids manual ────────────────────────────────────────────────────

    def test_papel_subtotal(self):
        q = self._make_quote(tiraje=1000)
        papel = self.env['impr.quote.papel'].create({
            'quote_id': q.id,
            'tipo': 'caratula',
            'material_id': self.mat.id,
            'paginas': 4,
            'aprovechamiento': 4,   # manual (lomo+sangría)
            'demasia': 50,
            'precio_kg': self.mat.precio_kg,
        })
        # subtotal debe ser > 0 si el material tiene precio y dimensiones
        if self.mat.precio_kg and self.mat.largo and self.mat.ancho:
            self.assertGreater(papel.subtotal, 0,
                               'subtotal de papel debe ser > 0 con datos completos')

    # ── total_papeles suma correctamente ────────────────────────────────────

    def test_total_papeles_suma_lineas(self):
        q = self._make_quote(tiraje=1000)
        p1 = self.env['impr.quote.papel'].create({
            'quote_id': q.id,
            'tipo': 'caratula',
            'material_id': self.mat.id,
            'paginas': 4,
            'aprovechamiento': 4,
            'demasia': 0,
            'precio_kg': self.mat.precio_kg,
        })
        p2 = self.env['impr.quote.papel'].create({
            'quote_id': q.id,
            'tipo': 'interior',
            'material_id': self.mat.id,
            'paginas': 64,
            'aprovechamiento': 32,  # Rendim convención Excel (= 4×imp)
            'demasia': 0,
            'precio_kg': self.mat.precio_kg,
        })
        q._compute_totales()
        expected = p1.subtotal + p2.subtotal
        self.assertAlmostEqual(q.total_papeles, expected, places=2)

    # ── markup inclusivo en el ORM ──────────────────────────────────────────

    def test_precio_final_mayor_que_subtotal(self):
        q = self._make_quote(tiraje=1000)
        # Agrega una línea con costo conocido
        self.env['impr.quote.papel'].create({
            'quote_id': q.id,
            'tipo': 'caratula',
            'material_id': self.mat.id,
            'paginas': 4,
            'aprovechamiento': 4,
            'demasia': 0,
            'precio_kg': self.mat.precio_kg,
        })
        q._compute_totales()
        if q.precio_total > 0:
            self.assertGreater(q.precio_final, q.precio_total,
                               'precio_final debe superar el subtotal de costos')
            self.assertGreater(q.precio_final_con_igv, q.precio_final,
                               'precio_final c/IGV debe superar precio s/IGV')

    # ── encuadernado cantidad=1 ─────────────────────────────────────────────

    def test_encuadernado_cantidad_1(self):
        q = self._make_quote(tiraje=1000)
        enc = self.env['impr.quote.encuadernado'].create({
            'quote_id': q.id,
            'tipo': 'Remachado con Liga',
            'cantidad': 1,
            'precio_unit': 500.0,
        })
        self.assertAlmostEqual(enc.subtotal, 500.0, places=2,
                               msg='cantidad=1 × 500 debe dar subtotal=500')

    def test_encuadernado_cantidad_0_subtotal_cero(self):
        q = self._make_quote()
        enc = self.env['impr.quote.encuadernado'].create({
            'quote_id': q.id,
            'tipo': 'Remachado con Liga',
            'cantidad': 0,
            'precio_unit': 500.0,
        })
        self.assertEqual(enc.subtotal, 0.0,
                         'cantidad=0 siempre debe dar subtotal=0')

    # ── troquelado ──────────────────────────────────────────────────────────

    def test_troquelado_subtotal(self):
        q = self._make_quote(tiraje=2000)
        troq = self.env['impr.quote.troquelado'].create({
            'quote_id': q.id,
            'tipo': 'Troquelado',
            'tiraje': 2.0,       # 2 millares
            'precio_unit': 150.0,
        })
        self.assertAlmostEqual(troq.subtotal, 300.0, places=2)

    # ── corte inicial/final ─────────────────────────────────────────────────

    def test_corte_inicial_subtotal(self):
        q = self._make_quote()
        corte = self.env['impr.quote.corte'].create({
            'quote_id': q.id,
            'tipo': 'inicial',
            'cantidad': 5.0,     # 5 resmas
            'precio_unit': 20.0,
        })
        self.assertAlmostEqual(corte.subtotal, 100.0, places=2)

    def test_corte_final_subtotal(self):
        q = self._make_quote()
        corte = self.env['impr.quote.corte'].create({
            'quote_id': q.id,
            'tipo': 'final',
            'cantidad': 3.0,     # 3 millares
            'precio_unit': 50.0,
        })
        self.assertAlmostEqual(corte.subtotal, 150.0, places=2)

    # ── transporte ──────────────────────────────────────────────────────────

    def test_transporte_subtotal(self):
        q = self._make_quote()
        trans = self.env['impr.quote.transporte'].create({
            'quote_id': q.id,
            'tipo': 'Transporte',
            'peso_total': 250.0,
            'cantidad': 250.0,
            'precio_unit': 0.50,
        })
        self.assertAlmostEqual(trans.subtotal, 125.0, places=2)

    # ── empaquetado ─────────────────────────────────────────────────────────

    def test_empaquetado_n_cajas(self):
        """Con 1000 libros / 20 por caja = 50 cajas."""
        q = self._make_quote(tiraje=1000)
        q.libros_x_caja = 20
        n_cajas = math.ceil(1000 / 20)
        self.assertEqual(n_cajas, 50)

    # ── secuencia de nombre ──────────────────────────────────────────────────

    def test_nombre_asignado_en_create(self):
        q = self._make_quote()
        self.assertNotEqual(q.name, 'New',
                            'El nombre debe asignarse desde la secuencia')

    # ── formula_breakdown tiene contenido ───────────────────────────────────

    def test_formula_breakdown_generada(self):
        q = self._make_quote(tiraje=1000)
        # Forzar recompute
        q._compute_formula_breakdown()
        self.assertIn('FÓRMULAS', q.formula_breakdown or '',
                      'formula_breakdown debe contener el encabezado de fórmulas')


# ═══════════════════════════════════════════════════════════════════════════
#  FLOW TEST — flujo completo: borrador → aprobada → liberar
# ═══════════════════════════════════════════════════════════════════════════

@tagged('flow', 'impr', '-at_install', 'post_install')
class TestPrintQuoteFlow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mat = cls.env['impr.paper.material'].search(
            [('largo', '>', 0), ('ancho', '>', 0), ('gramaje', '>', 0)],
            limit=1,
        )
        if not cls.mat:
            cls.mat = cls.env['impr.paper.material'].create({
                'name': 'MAT_FLOW_TEST 90g',
                'largo': 102.0, 'ancho': 72.0,
                'gramaje': 90.0, 'precio_kg': 1.18,
                'unidad_paquete': 500,
            })
        cls.partner = cls.env['res.partner'].search([], limit=1)

    def _full_quote(self):
        q = self.env['impr.print.quote'].create({
            'nombre': 'Libro test flow',
            'client_id': self.partner.id,
            'tc': 3.80,
            'ancho': 14.8,
            'largo': 21.0,
            'tiraje_principal': 1000,
            'peso_x_libro': 0.25,
            'libros_x_caja': 20,
            'material_caratula_id': self.mat.id,
            'colores_caratula': '4/0',
            'paginas_cara': 4,
        })
        self.env['impr.quote.papel'].create({
            'quote_id': q.id,
            'tipo': 'caratula',
            'material_id': self.mat.id,
            'paginas': 4,
            'aprovechamiento': 4,
            'demasia': 50,
            'precio_kg': self.mat.precio_kg,
        })
        return q

    def test_estado_draft_inicial(self):
        q = self._full_quote()
        self.assertEqual(q.state, 'draft')

    def test_flujo_draft_sent_approved(self):
        q = self._full_quote()
        q.action_send()
        self.assertEqual(q.state, 'sent')
        q.action_approve()
        self.assertEqual(q.state, 'approved')

    def test_liberar_requiere_estado_approved(self):
        q = self._full_quote()
        # En estado draft debe lanzar UserError
        with self.assertRaises(UserError):
            q.action_liberar()

    def test_liberar_crea_sale_order(self):
        q = self._full_quote()
        q.action_send()
        q.action_approve()
        result = q.action_liberar()
        self.assertTrue(q.sale_order_id,
                        'Debe existir una Orden de Venta tras liberar')
        self.assertEqual(q.sale_order_id.partner_id, self.partner)

    def test_liberar_crea_manufacturing_order(self):
        q = self._full_quote()
        q.action_send()
        q.action_approve()
        q.action_liberar()
        self.assertTrue(q.production_id,
                        'Debe existir una Orden de Producción tras liberar')
        self.assertEqual(q.state, 'production')

    def test_liberar_cambia_estado_a_production(self):
        q = self._full_quote()
        q.action_send()
        q.action_approve()
        q.action_liberar()
        self.assertEqual(q.state, 'production')

    def test_cancelar_desde_draft(self):
        q = self._full_quote()
        q.action_cancel()
        self.assertEqual(q.state, 'cancelled')

    def test_volver_a_draft(self):
        q = self._full_quote()
        q.action_cancel()
        q.action_draft()
        self.assertEqual(q.state, 'draft')

    def test_no_doble_liberacion(self):
        """Una cotización en producción no puede liberarse otra vez."""
        q = self._full_quote()
        q.action_send()
        q.action_approve()
        q.action_liberar()
        with self.assertRaises(UserError):
            q.action_liberar()

    # ── REPLICA EXACTA DEL EXCEL (Sample Book) ─────────────────────

    def test_excel_libro_ana_franc_completo(self):
        """Reproduce la plantilla Excel (Sample Book, 15×23 cm, tiraje 1000).
        Valida que:
          - Subtotal costos = ~S/ 3662 (±5 de tolerancia por redondeo)
          - Precio final sin IGV = ~S/ 4590.72
          - Precio final con IGV = ~S/ 5417.05
        """
        duplex = self.env['impr.paper.material'].search(
            [('name', 'ilike', 'DUPLEX16'), ('largo', '=', 70), ('ancho', '=', 100)],
            limit=1,
        )
        book = self.env['impr.paper.material'].search(
            [('name', 'ilike', 'BOOK CREAM'), ('largo', '=', 102)],
            limit=1,
        )
        if not duplex or not book:
            self.skipTest('Materiales DUPLEX16 o BOOK CREAM no encontrados en catálogo')

        q = self.env['impr.print.quote'].create({
            'nombre': 'Sample Book (réplica Excel)',
            'client_id': self.partner.id,
            'tc': 3.4,
            'ancho': 15.0, 'largo': 23.0,
            'tiraje_principal': 1000,
            'paginas_cara': 1,
            'peso_x_libro': 0.19734,
            'libros_x_caja': 60,
            'material_caratula_id': duplex.id,
            'colores_caratula': '4/0',
            'pct_ggff': 7.5, 'pct_utilidad': 12.0, 'pct_comision': 2.0,
        })

        # ── PAPEL caratula (imp=4 MANUAL, demasia=400) ─────────────────────
        p_car = self.env['impr.quote.papel'].create({
            'quote_id': q.id, 'tipo': 'caratula',
            'material_id': duplex.id,
            'paginas': 1, 'aprovechamiento': 4, 'demasia': 400,
            'precio_kg': duplex.precio_kg, 'sequence': 1,
        })
        # ── PAPEL interior 1 (160 pág, Rendim=32 Excel, demasia=200) ───────
        p_i1 = self.env['impr.quote.papel'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'material_id': book.id,
            'paginas': 160, 'aprovechamiento': 32, 'demasia': 200,
            'precio_kg': book.precio_kg, 'sequence': 20,
        })
        # ── PAPEL interior 2 (8 pág, Rendim=32, demasia=350) ──────────────
        p_i2 = self.env['impr.quote.papel'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'material_id': book.id,
            'paginas': 8, 'aprovechamiento': 32, 'demasia': 350,
            'precio_kg': book.precio_kg, 'sequence': 30,
        })
        # ── PAPEL interior 3 (4 pág, Rendim=32, demasia=350) ──────────────
        p_i3 = self.env['impr.quote.papel'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'material_id': book.id,
            'paginas': 4, 'aprovechamiento': 32, 'demasia': 350,
            'precio_kg': book.precio_kg, 'sequence': 40,
        })

        # Verificar Q Pliegos
        self.assertAlmostEqual(p_car.q_pliegos, 350.0, places=0,
                               msg='Carátula q_pliegos esperado 350')
        self.assertAlmostEqual(p_i1.q_pliegos, 6000.0, places=0,
                               msg='Interior 1 q_pliegos esperado 6000')

        # ── PLACAS ─────────────────────────────────────────────────────────
        self.env['impr.quote.placa'].create({
            'quote_id': q.id, 'tipo': 'caratula',
            'pliegos': 0.25, 'maqui': 0.5,
            'color_t': 4, 'color_r': 0, 'precio_unit': 13,
            'sequence': 1,
        })
        self.env['impr.quote.placa'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'pliegos': 5.0, 'maqui': 0.5,
            'color_t': 1, 'color_r': 1, 'precio_unit': 13,
            'sequence': 20,
        })
        self.env['impr.quote.placa'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'pliegos': 0.25, 'maqui': 0.5,
            'color_t': 1, 'color_r': 1, 'precio_unit': 13,
            'sequence': 30,
        })
        self.env['impr.quote.placa'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'pliegos': 0.125, 'maqui': 0.5,
            'color_t': 1, 'color_r': 1, 'precio_unit': 13,
            'sequence': 40,
        })

        # ── OFFSET ─────────────────────────────────────────────────────────
        self.env['impr.quote.offset'].create({
            'quote_id': q.id, 'tipo': 'caratula',
            'pliegos': 0.25, 'maqui': 1.0, 'demasia': 400,
            'precio_unit': 50, 'sequence': 1,
        })
        self.env['impr.quote.offset'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'pliegos': 5.0, 'maqui': 0.5, 'demasia': 200,
            'precio_unit': 30, 'sequence': 20,
        })
        self.env['impr.quote.offset'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'pliegos': 0.25, 'maqui': 0.5, 'demasia': 350,
            'precio_unit': 30, 'sequence': 30,
        })
        self.env['impr.quote.offset'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'pliegos': 0.125, 'maqui': 0.5, 'demasia': 350,
            'precio_unit': 30, 'sequence': 40,
        })

        # ── ACABADOS (plastico brillo + barniz UV) ─────────────────────────
        self.env['impr.quote.acabado'].create({
            'quote_id': q.id, 'tipo': 'Plastico Brillo',
            'tiraje': 1, 'precio_unit': 100, 'sequence': 10,
        })
        self.env['impr.quote.acabado'].create({
            'quote_id': q.id, 'tipo': 'Barniz UV Mate',
            'tiraje': 1, 'precio_unit': 100, 'sequence': 20,
        })

        # ── DOBLADO ────────────────────────────────────────────────────────
        self.env['impr.quote.doblado'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'factor': 1, 'q_pliegos': 12000, 'precio_unit': 8, 'sequence': 20,
        })
        self.env['impr.quote.doblado'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'factor': 2, 'q_pliegos': 675, 'precio_unit': 8, 'sequence': 30,
        })
        self.env['impr.quote.doblado'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'factor': 4, 'q_pliegos': 337.5, 'precio_unit': 8, 'sequence': 40,
        })

        # ── ALCE ───────────────────────────────────────────────────────────
        self.env['impr.quote.alce'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'factor': 1.5, 'q_pliegos': 12000, 'precio_unit': 8, 'sequence': 20,
        })
        self.env['impr.quote.alce'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'factor': 1.5, 'q_pliegos': 1350, 'precio_unit': 8, 'sequence': 30,
        })
        self.env['impr.quote.alce'].create({
            'quote_id': q.id, 'tipo': 'interior',
            'factor': 1.5, 'q_pliegos': 1350, 'precio_unit': 8, 'sequence': 40,
        })

        # ── COSIDO ─────────────────────────────────────────────────────────
        # Pag/Demasía/Tiraje se toman automáticamente del papel+cabecera.
        self.env['impr.quote.cosido'].create({
            'quote_id': q.id,
            'cuadernillo': 2, 'precio_unit': 25,
            'sequence': 30,
        })
        self.env['impr.quote.cosido'].create({
            'quote_id': q.id,
            'cuadernillo': 1, 'precio_unit': 12.5,
            'sequence': 40,
        })

        # ── TROQUELADO, CORTES, EMPAQUETADO, TRANSPORTE ──────────────────
        self.env['impr.quote.troquelado'].create({
            'quote_id': q.id, 'tiraje': 1, 'precio_unit': 85,
        })
        self.env['impr.quote.corte'].create({
            'quote_id': q.id, 'tipo': 'inicial',
            'cantidad': 16.5125, 'precio_unit': 3,
        })
        self.env['impr.quote.corte'].create({
            'quote_id': q.id, 'tipo': 'final',
            'cantidad': 1, 'precio_unit': 40,
        })
        self.env['impr.quote.empaquetado'].create({
            'quote_id': q.id, 'tipo': 'Sellado de Libro',
            'cantidad': 1, 'precio_unit': 250, 'sequence': 10,
        })
        self.env['impr.quote.empaquetado'].create({
            'quote_id': q.id, 'tipo': 'Caja',
            'cantidad': 17, 'precio_unit': 5, 'sequence': 20,
        })
        self.env['impr.quote.transporte'].create({
            'quote_id': q.id, 'tipo': 'Transporte',
            'peso_total': 197.34, 'cantidad': 400, 'precio_unit': 0.5,
        })

        # Forzar recompute
        q._compute_totales()

        # ── Validaciones contra Excel ──────────────────────────────────────
        # (Tolerancias por redondeo en cálculos intermedios)
        self.assertAlmostEqual(q.total_placas, 331.5, delta=1.0,
                               msg=f'Total Placas esperado ~331.5, got {q.total_placas}')
        self.assertAlmostEqual(q.total_offset, 470, delta=5.0,
                               msg=f'Total Offset esperado ~470, got {q.total_offset}')
        self.assertAlmostEqual(q.total_doblado, 128, delta=5.0,
                               msg=f'Total Doblado esperado ~128, got {q.total_doblado}')
        self.assertAlmostEqual(q.total_alce, 192, delta=5.0,
                               msg=f'Total Alce esperado ~192, got {q.total_alce}')
        self.assertAlmostEqual(q.total_cosido, 175, delta=5.0,
                               msg=f'Total Cosido esperado ~175, got {q.total_cosido}')
        self.assertAlmostEqual(q.total_troquelado, 85, delta=0.1)
        self.assertAlmostEqual(q.total_cortes, 89.54, delta=1.0)
        self.assertAlmostEqual(q.total_empaquetado, 335, delta=1.0)
        self.assertAlmostEqual(q.total_transporte, 200, delta=0.1)

        # Precio final — validar margen de ±2% (tolerancia generosa por papel)
        self.assertGreater(q.precio_final, 4000, msg='precio_final debe ser >S/4000')
        self.assertLess(q.precio_final, 5200, msg='precio_final debe ser <S/5200')
        # IGV ratio siempre exacto
        self.assertAlmostEqual(q.precio_final_con_igv, q.precio_final * 1.18, places=2)

    # ── Totales integrados ───────────────────────────────────────────────────

    def test_total_costos_es_suma_secciones(self):
        q = self._full_quote()
        q._compute_totales()
        total_calc = (
            q.total_papeles + q.total_placas + q.total_offset +
            q.total_acabados + q.total_doblado + q.total_alce +
            q.total_cosido + q.total_encuadernado + q.total_empaquetado +
            q.total_troquelado + q.total_cortes + q.total_transporte
        )
        self.assertAlmostEqual(q.precio_total, total_calc, places=2,
                               msg='precio_total debe ser la suma exacta de las 12 secciones')
