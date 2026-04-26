from odoo import models, fields, api


class ImprDetraccionTipo(models.Model):
    _name = 'impr.detraccion.tipo'
    _description = 'Tipo de Detracción SUNAT (SPOT)'
    _order = 'anexo, codigo'
    _rec_name = 'display_name'

    codigo = fields.Char(
        string='Código SUNAT',
        size=3,
        required=True,
        help='Código asignado por SUNAT al tipo de operación (ej. 037, 027, 020).',
    )
    name = fields.Char(
        string='Descripción',
        required=True,
    )
    porcentaje = fields.Float(
        string='Porcentaje',
        required=True,
        digits=(5, 2),
        help='Tasa de detracción aplicable (%).',
    )
    umbral = fields.Monetary(
        string='Umbral mínimo',
        default=700.0,
        currency_field='currency_id',
        help='Monto mínimo de la operación a partir del cual aplica la detracción.',
    )
    currency_id = fields.Many2one(
        'res.currency',
        default=lambda self: (
            self.env.ref('base.PEN', raise_if_not_found=False)
            or self.env.company.currency_id
        ),
    )
    anexo = fields.Selection(
        [
            ('2', 'Anexo 2 — Bienes'),
            ('3', 'Anexo 3 — Servicios'),
            ('otros', 'Otros'),
        ],
        string='Anexo',
        required=True,
        default='3',
    )
    active = fields.Boolean(string='Activo', default=True)
    notas = fields.Text(string='Notas')

    display_name = fields.Char(
        string='Nombre',
        compute='_compute_display_name',
        store=True,
    )

    _sql_constraints = [
        ('codigo_unique', 'unique(codigo)', 'Ya existe un tipo de detracción con ese código SUNAT.'),
    ]

    @api.depends('codigo', 'name', 'porcentaje')
    def _compute_display_name(self):
        for r in self:
            if r.codigo and r.name:
                r.display_name = f'{r.codigo} — {r.name} ({r.porcentaje:.0f}%)'
            else:
                r.display_name = r.name or ''
