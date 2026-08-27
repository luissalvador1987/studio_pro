# -*- coding: utf-8 -*-
"""Export everything built for an App as a real, installable Odoo module.

Scope (v1): models, custom fields, views, window actions, menus, groups and
access rights — the structural backbone of an App, exactly what Odoo
Studio's own "Export" produces. Automations and generated reports are *not*
re-serialized here yet (they often reference environment-specific things
like webhook URLs or mail templates); they keep working in this database,
and can be recreated by hand in the target one for now.
"""
import base64
import io
import re
import zipfile
from xml.sax.saxutils import escape

from odoo import api, fields, models
from odoo.exceptions import UserError


def esc(value):
    return escape(str(value if value is not None else ''))


class StudioExportWizard(models.TransientModel):
    _name = 'studio.export.wizard'
    _description = 'Studio Pro — Exportar App como Módulo'

    app_id = fields.Many2one('studio.app', string="App", required=True)
    module_name = fields.Char(string="Nombre del módulo", compute='_compute_module_name', store=True, readonly=False)
    state = fields.Selection([('draft', 'Borrador'), ('done', 'Hecho')], string="Estado", default='draft')
    file_data = fields.Binary(string="Archivo", readonly=True, attachment=False)
    file_name = fields.Char(string="Nombre del archivo", readonly=True)

    @api.depends('app_id')
    def _compute_module_name(self):
        for wiz in self:
            if not wiz.module_name and wiz.app_id:
                wiz.module_name = 'studio_export_%s' % (wiz.app_id.technical_name or 'app')

    # ------------------------------------------------------------------
    def _xmlid_for(self, record, prefix):
        IMD = self.env['ir.model.data'].sudo()
        existing = IMD.search([('model', '=', record._name), ('res_id', '=', record.id)], limit=1)
        if existing:
            return '%s.%s' % (existing.module, existing.name)
        name = re.sub(r'[^a-zA-Z0-9_]', '_', '%s_%s' % (prefix, record.id))
        IMD.create({
            'module': self.module_name, 'name': name,
            'model': record._name, 'res_id': record.id, 'noupdate': True,
        })
        return '%s.%s' % (self.module_name, name)

    def action_generate(self):
        self.ensure_one()
        if not self.module_name:
            raise UserError(self.env._("Indica un nombre técnico para el módulo exportado."))
        app = self.app_id
        if not app.model_ids:
            raise UserError(self.env._("Esta app todavía no tiene modelos para exportar."))

        blocks = []
        for model in app.model_ids:
            blocks.append(self._export_model(model))
        for model in app.model_ids:
            for field in model.field_id.filtered(lambda f: f.state == 'manual' and f.name != 'x_name'):
                blocks.append(self._export_field(field))

        model_names = app.model_ids.mapped('model')
        views = self.env['ir.ui.view'].sudo().search([('model', 'in', model_names)])
        for view in views:
            blocks.append(self._export_view(view))

        actions = self.env['ir.actions.act_window'].sudo().search([('res_model', 'in', model_names)])
        for action in actions:
            blocks.append(self._export_action(action))

        menus = self.env['ir.ui.menu'].sudo().search([('id', 'child_of', app.menu_id.id)]) if app.menu_id \
            else self.env['ir.ui.menu'].sudo().browse()
        for menu in menus:
            blocks.append(self._export_menu(menu, actions))

        groups = app.manager_group_id + app.user_group_id
        for group in groups:
            blocks.append(self._export_group(group))

        accesses = self.env['ir.model.access'].sudo().search([('group_id', 'in', groups.ids)])
        for access in accesses:
            blocks.append(self._export_access(access))

        data_xml = '<?xml version="1.0" encoding="utf-8"?>\n<odoo noupdate="1">\n%s\n</odoo>\n' % "\n".join(blocks)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('%s/__init__.py' % self.module_name, '')
            zf.writestr('%s/__manifest__.py' % self.module_name, self._build_manifest())
            zf.writestr('%s/data/studio_export_data.xml' % self.module_name, data_xml)

        self.write({
            'state': 'done',
            'file_data': base64.b64encode(buf.getvalue()),
            'file_name': '%s.zip' % self.module_name,
        })
        self.env['studio.change'].log(
            'app', 'studio.app', app.id, action='update', app_id=app.id,
            summary="App '%s' exportada como módulo '%s'" % (app.name, self.module_name))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'studio.export.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _build_manifest(self):
        return (
            "{\n"
            "    'name': %r,\n"
            "    'version': '18.0.1.0.0',\n"
            "    'category': 'Customizations',\n"
            "    'summary': 'Exportado desde Studio Pro',\n"
            "    'depends': ['base', 'mail'],\n"
            "    'data': ['data/studio_export_data.xml'],\n"
            "    'installable': True,\n"
            "    'license': 'LGPL-3',\n"
            "}\n"
        ) % (self.app_id.name,)

    # ------------------------------------------------------------------
    # per-model serializers
    # ------------------------------------------------------------------
    def _export_model(self, model):
        xmlid = self._xmlid_for(model, 'model_%s' % model.model.replace('.', '_'))
        return (
            '  <record id="%s" model="ir.model">\n'
            '    <field name="name">%s</field>\n'
            '    <field name="model">%s</field>\n'
            '    <field name="state">manual</field>\n'
            '  </record>'
        ) % (xmlid.split('.', 1)[1], esc(model.name), esc(model.model))

    def _export_field(self, field):
        xmlid = self._xmlid_for(field, 'field_%s_%s' % (field.model.replace('.', '_'), field.name))
        model_xmlid = self._xmlid_for(field.model_id, 'model_%s' % field.model.replace('.', '_'))
        lines = [
            '  <record id="%s" model="ir.model.fields">' % xmlid.split('.', 1)[1],
            '    <field name="name">%s</field>' % esc(field.name),
            '    <field name="field_description">%s</field>' % esc(field.field_description),
            '    <field name="ttype">%s</field>' % esc(field.ttype),
            '    <field name="model_id" ref="%s"/>' % model_xmlid,
            '    <field name="state">manual</field>',
        ]
        if field.required:
            lines.append('    <field name="required" eval="True"/>')
        if field.relation:
            lines.append('    <field name="relation">%s</field>' % esc(field.relation))
        if field.relation_field:
            lines.append('    <field name="relation_field">%s</field>' % esc(field.relation_field))
        lines.append('  </record>')

        for selection in field.selection_ids:
            sel_xmlid = self._xmlid_for(selection, 'selection_%s_%s' % (field.name, selection.id))
            lines.append('  <record id="%s" model="ir.model.fields.selection">' % sel_xmlid.split('.', 1)[1])
            lines.append('    <field name="field_id" ref="%s"/>' % xmlid)
            lines.append('    <field name="value">%s</field>' % esc(selection.value))
            lines.append('    <field name="name">%s</field>' % esc(selection.name))
            lines.append('    <field name="sequence">%s</field>' % selection.sequence)
            lines.append('  </record>')
        return "\n".join(lines)

    def _export_view(self, view):
        xmlid = self._xmlid_for(view, 'view_%s_%s' % (view.model.replace('.', '_'), view.type))
        return (
            '  <record id="%s" model="ir.ui.view">\n'
            '    <field name="name">%s</field>\n'
            '    <field name="model">%s</field>\n'
            '    <field name="type">%s</field>\n'
            '    <field name="arch" type="xml">%s</field>\n'
            '  </record>'
        ) % (xmlid.split('.', 1)[1], esc(view.name), esc(view.model), esc(view.type), view.arch or '')

    def _export_action(self, action):
        xmlid = self._xmlid_for(action, 'action_%s' % action.res_model.replace('.', '_'))
        return (
            '  <record id="%s" model="ir.actions.act_window">\n'
            '    <field name="name">%s</field>\n'
            '    <field name="res_model">%s</field>\n'
            '    <field name="view_mode">%s</field>\n'
            '  </record>'
        ) % (xmlid.split('.', 1)[1], esc(action.name), esc(action.res_model), esc(action.view_mode))

    def _export_menu(self, menu, actions):
        xmlid = self._xmlid_for(menu, 'menu_%s' % menu.id)
        lines = [
            '  <record id="%s" model="ir.ui.menu">' % xmlid.split('.', 1)[1],
            '    <field name="name">%s</field>' % esc(menu.name),
            '    <field name="sequence">%s</field>' % menu.sequence,
        ]
        if menu.parent_id:
            parent_xmlid = self._xmlid_for(menu.parent_id, 'menu_%s' % menu.parent_id.id)
            lines.append('    <field name="parent_id" ref="%s"/>' % parent_xmlid)
        if menu.action and menu.action.res_model in actions.mapped('res_model'):
            action = actions.filtered(lambda a: a.id == menu.action.id)
            if action:
                action_xmlid = self._xmlid_for(action, 'action_%s' % action.res_model.replace('.', '_'))
                lines.append('    <field name="action" ref="%s"/>' % action_xmlid)
        lines.append('  </record>')
        return "\n".join(lines)

    def _export_group(self, group):
        xmlid = self._xmlid_for(group, 'group_%s' % group.id)
        return (
            '  <record id="%s" model="res.groups">\n'
            '    <field name="name">%s</field>\n'
            '  </record>'
        ) % (xmlid.split('.', 1)[1], esc(group.name))

    def _export_access(self, access):
        xmlid = self._xmlid_for(access, 'access_%s' % access.id)
        model_xmlid = self._xmlid_for(access.model_id, 'model_%s' % access.model_id.model.replace('.', '_'))
        group_xmlid = self._xmlid_for(access.group_id, 'group_%s' % access.group_id.id)
        return (
            '  <record id="%s" model="ir.model.access">\n'
            '    <field name="name">%s</field>\n'
            '    <field name="model_id" ref="%s"/>\n'
            '    <field name="group_id" ref="%s"/>\n'
            '    <field name="perm_read" eval="%s"/>\n'
            '    <field name="perm_write" eval="%s"/>\n'
            '    <field name="perm_create" eval="%s"/>\n'
            '    <field name="perm_unlink" eval="%s"/>\n'
            '  </record>'
        ) % (xmlid.split('.', 1)[1], esc(access.name), model_xmlid, group_xmlid,
             access.perm_read, access.perm_write, access.perm_create, access.perm_unlink)
