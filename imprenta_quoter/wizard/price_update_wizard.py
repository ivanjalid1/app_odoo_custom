from odoo import models, fields, api


class ImprPriceUpdateWizard(models.TransientModel):
    _name = 'impr.price.update.wizard'
    _description = 'Asistente para actualización masiva de precios de materiales'

    line_ids = fields.One2many(
        'impr.price.update.wizard.line', 'wizard_id', string='Materiales',
    )
    update_type = fields.Selection([
        ('percentage', 'Porcentaje'),
        ('manual', 'Manual'),
    ], string='Tipo de actualización', default='percentage', required=True)
    percentage = fields.Float('Porcentaje (%)', default=0.0)

    def action_load_materials(self):
        """Carga todos los materiales activos en las líneas del wizard."""
        self.line_ids = [(5, 0, 0)]
        materials = self.env['impr.paper.material'].search([('active', '=', True)])
        lines = []
        for mat in materials:
            lines.append((0, 0, {
                'material_id': mat.id,
                'new_price': mat.precio_kg,
            }))
        self.line_ids = lines
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply_percentage(self):
        """Aplica el porcentaje a todas las líneas: new_price = current * (1 + %/100)."""
        for line in self.line_ids:
            line.new_price = line.current_price * (1 + self.percentage / 100)
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_update_prices(self):
        """Escribe el nuevo precio en cada material y cierra el wizard."""
        for line in self.line_ids:
            if line.material_id and line.new_price != line.current_price:
                line.material_id.precio_kg = line.new_price
        return {'type': 'ir.actions.act_window_close'}


class ImprPriceUpdateWizardLine(models.TransientModel):
    _name = 'impr.price.update.wizard.line'
    _description = 'Línea del asistente de actualización de precios'

    wizard_id = fields.Many2one(
        'impr.price.update.wizard', string='Wizard', ondelete='cascade',
    )
    material_id = fields.Many2one(
        'impr.paper.material', string='Material', required=True,
    )
    name = fields.Char(related='material_id.name', string='Nombre', readonly=True)
    current_price = fields.Float(
        related='material_id.precio_kg', string='Precio actual', readonly=True,
    )
    new_price = fields.Float('Nuevo precio')
