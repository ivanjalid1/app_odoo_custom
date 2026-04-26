from odoo import models, fields, api


class ImprQuoteTransporte(models.Model):
    _name = 'impr.quote.transporte'
    _description = 'Línea de transporte en cotización'
    _order = 'sequence, id'

    quote_id = fields.Many2one('impr.print.quote', ondelete='cascade', required=True)
    sequence = fields.Integer(default=10)
    tipo = fields.Char('Tipo')
    peso_total = fields.Float('Peso Total', digits=(12, 2))
    cantidad = fields.Float('Cantidad', digits=(12, 2))
    precio_unit = fields.Float('P Unit', digits=(12, 2))
    subtotal = fields.Float('P Total', digits=(12, 2), compute='_compute_subtotal', store=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Persistir peso_total, cantidad y precio_unit en DB al crear."""
        for vals in vals_list:
            qid = vals.get('quote_id')
            if qid:
                q = self.env['impr.print.quote'].browse(qid)
                if not vals.get('peso_total'):
                    vals['peso_total'] = q.peso_total or 0
                if not vals.get('cantidad'):
                    vals['cantidad'] = ImprQuoteTransporte._flete_minimo(vals.get('peso_total', 0))
                if not vals.get('precio_unit'):
                    vals['precio_unit'] = 0.50
        return super().create(vals_list)

    @api.onchange('tipo')
    def _onchange_fill(self):
        """Llena en vivo para UI. No pisa si ya tiene valores."""
        if not self.quote_id or self.peso_total:
            return
        self.peso_total = self.quote_id.peso_total or 0
        self.cantidad = self._flete_minimo(self.peso_total)
        if not self.precio_unit:
            self.precio_unit = 0.50

    @staticmethod
    def _flete_minimo(peso):
        """Excel M107: =IF(D107<2000,400,IF(D107<5000,600,IF(D107<7000,1000,
           IF(D107<10000,1200,IF(D107<12000,1700,1)))))"""
        if peso < 2000:
            return 400
        if peso < 5000:
            return 600
        if peso < 7000:
            return 1000
        if peso < 10000:
            return 1200
        if peso < 12000:
            return 1700
        return peso

    @api.depends('cantidad', 'precio_unit')
    def _compute_subtotal(self):
        for r in self:
            r.subtotal = (r.cantidad or 0) * (r.precio_unit or 0)
