# -*- coding: utf-8 -*-
from odoo import fields, models


class StudioNewViewWizard(models.TransientModel):
    _name = 'studio.new.view.wizard'
    _description = 'Studio Pro — Asistente de Nueva Vista'

    app_id = fields.Many2one('studio.app', string="App")
    res_model_id = fields.Many2one('ir.model', string="Modelo", required=True,
                                    help="Cualquier modelo: estándar, de otro addon, o creado con Studio Pro.")
    res_model_name = fields.Char(related='res_model_id.model')
    view_type = fields.Selection([
        ('form', 'Formulario'), ('list', 'Lista'), ('kanban', 'Kanban'),
        ('search', 'Búsqueda'), ('calendar', 'Calendario'),
        ('pivot', 'Tabla dinámica'), ('graph', 'Gráfico'), ('activity', 'Actividades'),
    ], string="Tipo de vista", required=True, default='form',
        help="No incluye Gantt: ese motor de vista (web_gantt) es exclusivo de Odoo Enterprise "
             "y no existe en Community, así que crear una vista de ese tipo acá no tendría con "
             "qué dibujarse en el navegador.")
    name = fields.Char(string="Nombre de la vista")

    def action_create(self):
        self.ensure_one()
        view = self.env['ir.ui.view'].studio_create_view(self.res_model_id.model, self.view_type, self.name)
        self.env['studio.change'].log(
            'view', 'ir.ui.view', view.id, action='create', app_id=self.app_id.id,
            summary="Vista '%s' (%s) creada para %s" % (view.name, self.view_type, self.res_model_id.model))

        if self.view_type in ('form', 'list'):
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'studio.view.editor.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_view_id': view.id},
            }
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.ui.view',
            'res_id': view.id,
            'view_mode': 'form',
        }
