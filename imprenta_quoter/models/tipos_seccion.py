"""Wrappers de conveniencia para tipos de sección.

Los datos viven en el modelo `impr.section.type` (editable desde
Configuración → Tipos de sección). Estas funciones evitan tener que escribir
`self.env['impr.section.type']._...()` en cada llamada.

Reglas:
  - Una sección "carátula" (es_caratula=True) usa maqui=1.0 y no participa de
    doblado/alce/cosido por defecto.
  - Cualquier otro tipo se comporta como interior (maqui=0.5, factor doblado=1,
    factor alce=1.5, aplica cosido).
"""


def get_tipo_selection(env):
    """Lista de tuplas (code, name) para usar en fields.Selection."""
    return env['impr.section.type']._selection_tipos()


def get_caratula_codes(env):
    """frozenset de códigos cuyas secciones se comportan como carátula."""
    return env['impr.section.type']._caratula_codes()


def es_caratula(env, code):
    """True si el código corresponde a una sección que se comporta como carátula."""
    return code in get_caratula_codes(env)


def es_interior(env, code):
    """True si se comporta como interior (cuerpo del libro)."""
    return bool(code) and code not in get_caratula_codes(env)
