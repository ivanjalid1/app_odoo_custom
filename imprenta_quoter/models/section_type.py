"""Catálogo editable de tipos de sección de cotización.

Reemplaza la lista hardcodeada `TIPO_SELECTION` de tipos_seccion.py.
Se gestiona desde Configuración → Tipos de sección.

El campo `tipo` en las líneas de cotización (papel/placa/offset/...) sigue siendo
fields.Selection y guarda el código como string — así no requiere migración de
datos. La lista de opciones se obtiene dinámicamente desde este modelo.
"""
from odoo import models, fields, api


class ImprSectionType(models.Model):
    _name = 'impr.section.type'
    _description = 'Tipo de sección de cotización'
    _order = 'sequence, name'

    name = fields.Char('Nombre', required=True, translate=True)
    code = fields.Char(
        'Código', required=True, copy=False,
        help='Código interno usado por la lógica de cálculo. Cambiarlo después de '
             'que existan cotizaciones con este tipo deja huérfanas las líneas '
             'que lo referencian.',
    )
    es_caratula = fields.Boolean(
        'Se comporta como carátula', default=False,
        help='Si está activado, esta sección usa las reglas de carátula '
             '(maqui=1.0, sin doblado/alce/cosido por defecto).',
    )
    sequence = fields.Integer('Secuencia', default=10)
    active = fields.Boolean('Activo', default=True)

    _sql_constraints = [
        ('code_uniq', 'UNIQUE(code)',
         'El código del tipo de sección debe ser único.'),
    ]

    @api.model
    def _selection_tipos(self):
        """Pares (code, name) para usar en fields.Selection.

        Incluye también los inactivos para que líneas existentes con un tipo
        archivado se sigan rindiendo correctamente en el form view.
        """
        recs = self.sudo().with_context(active_test=False).search([])
        return [(r.code, r.name) for r in recs]

    @api.model
    def _caratula_codes(self):
        """Conjunto inmutable de códigos cuyas secciones se comportan como carátula.

        No filtra por active: si se archiva un tipo, las cotizaciones existentes
        que lo usan deben seguir siendo tratadas correctamente.
        """
        return frozenset(
            self.sudo().with_context(active_test=False)
            .search([('es_caratula', '=', True)])
            .mapped('code')
        )
