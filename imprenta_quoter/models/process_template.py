from odoo import models, fields


class ImprProcessTemplate(models.Model):
    _name = 'impr.process.template'
    _description = 'Plantilla de proceso de producción'
    _order = 'sequence, name'

    name = fields.Char('Proceso', required=True)
    code = fields.Char('Código', required=True)
    sequence = fields.Integer('Secuencia', default=10)
    description = fields.Text('Descripción')
    workcenter_id = fields.Many2one(
        'mrp.workcenter', 'Centro de trabajo',
        help='Centro de trabajo por defecto para este proceso.',
    )
    people_default = fields.Integer('Personas (defecto)', default=1)
    duration_days_default = fields.Integer('Duración (días defecto)', default=1)
