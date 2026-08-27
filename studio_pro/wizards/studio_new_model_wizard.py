# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.studio_app import slugify_technical


class StudioNewModelWizard(models.TransientModel):
    _name = 'studio.new.model.wizard'
    _description = 'Studio Pro — Asistente de Nuevo Modelo'

    app_id = fields.Many2one('studio.app', string="App", required=True)
    name = fields.Char(required=True, string="Nombre del modelo", help="Ej: 'Equipo', 'Tarea del Proyecto'")
    technical_name_preview = fields.Char(compute='_compute_technical_name_preview', string="Nombre técnico")
    has_active_field = fields.Boolean(default=True, string="Archivado (campo Activo)")
    has_sequence_field = fields.Boolean(default=False, string="Orden manual (campo Secuencia)")
    has_description_field = fields.Boolean(default=False, string="Descripción (campo de texto largo)")

    @api.depends('name')
    def _compute_technical_name_preview(self):
        for wiz in self:
            wiz.technical_name_preview = slugify_technical(wiz.name, prefix='x_') if wiz.name else ''

    def action_create(self):
        self.ensure_one()
        if not self.app_id.state == 'active':
            self.app_id.action_activate()

        model_technical_name = slugify_technical(self.name, prefix='x_')
        if self.env['ir.model'].sudo().search_count([('model', '=', model_technical_name)]):
            raise UserError(self.env._("Ya existe un modelo llamado '%s'.") % model_technical_name)

        field_cmds = [(0, 0, {'name': 'x_name', 'field_description': 'Nombre', 'ttype': 'char', 'copied': True})]
        if self.has_active_field:
            field_cmds.append((0, 0, {
                'name': 'x_active', 'field_description': 'Activo', 'ttype': 'boolean', 'copied': True,
            }))
        if self.has_sequence_field:
            field_cmds.append((0, 0, {
                'name': 'x_sequence', 'field_description': 'Secuencia', 'ttype': 'integer', 'copied': True,
            }))
        if self.has_description_field:
            field_cmds.append((0, 0, {
                'name': 'x_studio_description', 'field_description': 'Descripción', 'ttype': 'text', 'copied': True,
            }))

        Model = self.env['ir.model'].sudo()
        model = Model.create({
            'name': self.name,
            'model': model_technical_name,
            'state': 'manual',
            'studio_app_id': self.app_id.id,
            'field_id': field_cmds,
        })
        # los campos manuales no admiten un `default=` a nivel Python; se usan
        # registros ir.default en su lugar, igual que la herramienta de
        # desarrollador "Definir Valores por Defecto".
        Default = self.env['ir.default'].sudo()
        if self.has_active_field:
            Default.set(model_technical_name, 'x_active', True)
        if self.has_sequence_field:
            Default.set(model_technical_name, 'x_sequence', 10)

        self._create_default_views(model)
        action = self._create_action(model)
        self._create_menu(model, action)
        self.app_id.grant_default_access(model)

        self.env['studio.change'].log(
            'model', 'ir.model', model.id, action='create', app_id=self.app_id.id,
            summary="Modelo '%s' (%s) creado" % (self.name, model_technical_name))

        return {
            'type': 'ir.actions.act_window',
            'name': model.name,
            'res_model': model.model,
            'view_mode': 'list,form',
        }

    def _create_default_views(self, model):
        has_active = 'x_active' in model.field_id.mapped('name')
        field_names = [f.name for f in model.field_id if f.name not in ('x_name',) and not f.name.startswith('message_')]

        form_fields = "".join('<field name="%s"/>' % n for n in field_names)
        form_arch = (
            '<form>'
            '<sheet>'
            '<group>'
            '<field name="x_name"/>'
            '%s'
            '</group>'
            '</sheet>'
            '</form>'
        ) % form_fields
        self.env['ir.ui.view'].sudo().create({
            'name': '%s.form (Studio Pro)' % model.model, 'type': 'form', 'model': model.model, 'arch': form_arch,
        })

        list_fields = "".join('<field name="%s"/>' % n for n in field_names if n != 'x_active')
        list_arch = '<list><field name="x_name"/>%s</list>' % list_fields
        self.env['ir.ui.view'].sudo().create({
            'name': '%s.list (Studio Pro)' % model.model, 'type': 'list', 'model': model.model, 'arch': list_arch,
        })

        search_arch = '<search><field name="x_name"/></search>'
        self.env['ir.ui.view'].sudo().create({
            'name': '%s.search (Studio Pro)' % model.model, 'type': 'search', 'model': model.model, 'arch': search_arch,
        })
        if has_active:
            # permite filtrar los registros archivados desde el primer momento
            self.env['ir.filters'].sudo().create({
                'name': 'Archivado', 'model_id': model.model, 'domain': "[('x_active', '=', False)]",
            })

    def _create_action(self, model):
        return self.env['ir.actions.act_window'].sudo().create({
            'name': model.name,
            'res_model': model.model,
            'view_mode': 'list,form',
        })

    def _create_menu(self, model, action):
        return self.env['ir.ui.menu'].sudo().create({
            'name': model.name,
            'parent_id': self.app_id.menu_id.id,
            'action': 'ir.actions.act_window,%d' % action.id,
        })
