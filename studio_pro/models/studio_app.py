# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError


def slugify_technical(name, prefix=''):
    """Turn a human label into a lowercase snake_case token, Studio-style."""
    slug = re.sub(r'[^a-z0-9]+', '_', (name or '').strip().lower()).strip('_')
    slug = re.sub(r'_+', '_', slug) or 'new'
    return '%s%s' % (prefix, slug)


class StudioApp(models.Model):
    _name = 'studio.app'
    _description = 'App de Studio Pro'
    _order = 'sequence, name'

    name = fields.Char(string="Nombre", required=True)
    technical_name = fields.Char(string="Nombre técnico", compute='_compute_technical_name', store=True,
                                  readonly=False,
                                  help="Identificador interno usado para el menú/categoría/grupos de esta app.")
    sequence = fields.Integer(default=10)
    icon = fields.Image(string="Icono", max_width=256, max_height=256)
    color = fields.Integer(default=0)
    description = fields.Text(string="Descripción")
    active = fields.Boolean(default=True)

    category_id = fields.Many2one('ir.module.category', string="Categoría", readonly=True, copy=False)
    menu_id = fields.Many2one('ir.ui.menu', string="Menú", readonly=True, copy=False)
    manager_group_id = fields.Many2one('res.groups', string="Grupo Administrador", readonly=True, copy=False)
    user_group_id = fields.Many2one('res.groups', string="Grupo Usuario", readonly=True, copy=False)

    model_ids = fields.One2many('ir.model', 'studio_app_id', string="Modelos")
    model_count = fields.Integer(string="Cantidad de modelos", compute='_compute_counts')
    automation_ids = fields.One2many('studio.automation.flow', 'app_id', string="Automatizaciones")
    automation_count = fields.Integer(string="Cantidad de automatizaciones", compute='_compute_counts')
    server_action_ids = fields.One2many('studio.server.action', 'app_id', string="Funciones")
    server_action_count = fields.Integer(string="Cantidad de funciones", compute='_compute_counts')
    report_ids = fields.One2many('studio.report.builder', 'app_id', string="Reportes")
    report_count = fields.Integer(string="Cantidad de reportes", compute='_compute_counts')
    dashboard_ids = fields.One2many('studio.dashboard', 'app_id', string="Tableros")
    dashboard_count = fields.Integer(string="Cantidad de tableros", compute='_compute_counts')
    change_ids = fields.One2many('studio.change', 'app_id', string="Historial de cambios")
    change_count = fields.Integer(string="Cantidad de cambios", compute='_compute_counts')

    state = fields.Selection([('draft', 'Borrador'), ('active', 'Activa')],
                              string="Estado", default='draft', readonly=True, copy=False)

    @api.depends('name')
    def _compute_technical_name(self):
        for app in self:
            if not app.technical_name and app.name:
                app.technical_name = slugify_technical(app.name)

    def _compute_counts(self):
        for app in self:
            app.model_count = len(app.model_ids)
            app.automation_count = len(app.automation_ids)
            app.server_action_count = len(app.server_action_ids)
            app.report_count = len(app.report_ids)
            app.dashboard_count = len(app.dashboard_ids)
            app.change_count = len(app.change_ids)

    def action_activate(self):
        """Provisiona la categoría, el menú principal y los grupos Administrador/Usuario
        de esta app. Es seguro llamarlo más de una vez (idempotente)."""
        # Studio Pro operates with elevated (sudo) rights for its own technical
        # scaffolding once a user has passed the group_studio_manager gate —
        # exactly like Odoo Studio itself: models such as ir.module.category
        # grant *no* group create/write rights at all by design (they're meant
        # to be managed via module data, not by hand), so without sudo() even
        # a System Administrator would get an access-rights error here.
        Groups = self.env['res.groups'].sudo()
        Category = self.env['ir.module.category'].sudo()
        Menu = self.env['ir.ui.menu'].sudo()
        for app in self:
            if not app.category_id:
                app.category_id = Category.create({'name': app.name, 'sequence': 50})
            if not app.manager_group_id:
                app.manager_group_id = Groups.create({
                    'name': 'Administrador',
                    'category_id': app.category_id.id,
                    'comment': "Acceso completo a los datos de la app '%s'." % app.name,
                })
            if not app.user_group_id:
                app.user_group_id = Groups.create({
                    'name': 'Usuario',
                    'category_id': app.category_id.id,
                    'comment': "Acceso básico a los datos de la app '%s'." % app.name,
                })
            if not app.menu_id:
                app.menu_id = Menu.create({
                    'name': app.name,
                    'sequence': app.sequence,
                    'web_icon_data': app.icon,
                })
            app.state = 'active'
            self.env['studio.change'].log(
                'app', 'studio.app', app.id, action='update', app_id=app.id,
                summary="App '%s' activada" % app.name)
        return True

    def action_open_models(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Modelos',
            'res_model': 'ir.model',
            'view_mode': 'list,form',
            'domain': [('studio_app_id', '=', self.id)],
            'context': {'default_studio_app_id': self.id},
        }

    def action_open_automations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Automatizaciones',
            'res_model': 'studio.automation.flow',
            'view_mode': 'list,form',
            'domain': [('app_id', '=', self.id)],
            'context': {'default_app_id': self.id},
        }

    def action_open_server_actions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Funciones',
            'res_model': 'studio.server.action',
            'view_mode': 'list,form',
            'domain': [('app_id', '=', self.id)],
            'context': {'default_app_id': self.id},
        }

    def action_open_reports(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Reportes',
            'res_model': 'studio.report.builder',
            'view_mode': 'list,form',
            'domain': [('app_id', '=', self.id)],
            'context': {'default_app_id': self.id},
        }

    def action_open_dashboards(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Tableros',
            'res_model': 'studio.dashboard',
            'view_mode': 'list,form',
            'domain': [('app_id', '=', self.id)],
            'context': {'default_app_id': self.id},
        }

    def action_open_access(self):
        self.ensure_one()
        groups = self.manager_group_id + self.user_group_id
        return {
            'type': 'ir.actions.act_window',
            'name': 'Permisos de acceso',
            'res_model': 'ir.model.access',
            'view_mode': 'list,form',
            'domain': [('group_id', 'in', groups.ids)],
            'context': {
                'default_group_id': self.manager_group_id.id,
                'search_default_group_id': self.manager_group_id.id,
            },
        }

    def action_open_change_log(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Historial de cambios',
            'res_model': 'studio.change',
            'view_mode': 'list,form',
            'domain': [('app_id', '=', self.id)],
        }

    def action_new_model(self):
        self.ensure_one()
        if not self.state == 'active':
            self.action_activate()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Nuevo modelo',
            'res_model': 'studio.new.model.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_app_id': self.id},
        }

    def grant_default_access(self, model):
        """Llamado por el asistente de creación de modelos justo después de crear un
        modelo dentro de esta app: da al grupo Administrador acceso CRUD completo y
        al grupo Usuario lectura/escritura/creación (sin eliminar) por defecto.
        """
        self.ensure_one()
        Access = self.env['ir.model.access'].sudo()
        if self.manager_group_id:
            Access.create({
                'name': '%s.manager' % model.model,
                'model_id': model.id,
                'group_id': self.manager_group_id.id,
                'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': True,
            })
        if self.user_group_id:
            Access.create({
                'name': '%s.user' % model.model,
                'model_id': model.id,
                'group_id': self.user_group_id.id,
                'perm_read': True, 'perm_write': True, 'perm_create': True, 'perm_unlink': False,
            })
