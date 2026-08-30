# -*- coding: utf-8 -*-
"""Export everything built for an App as a real, installable Odoo module,
laid out the way a hand-written module actually looks:

    my_module/
        __init__.py
        __manifest__.py
        hooks.py                       (only if there are DB constraints to (re)apply on install)
        data/models.xml                ir.model + ir.model.fields (+ selections)
        data/automations.xml           base.automation + their ir.actions.server
        data/server_actions.xml        studio.server.action's ir.actions.server (+ ir.cron)
        data/reports.xml               ir.actions.report + their QWeb ir.ui.view
        views/views.xml                ir.ui.view (regular ones) + ir.actions.act_window + ir.ui.menu
        security/security.xml          res.groups + ir.rule
        security/ir.model.access.csv   ir.model.access, as a real CSV — not XML records

Deliberately out of scope for this exporter (documented, not silently
missing): ``studio.custom.code`` (JS/CSS injection) is page/bundle-wide,
not tied to one App, so it is not bundled per-export — it already works on
this database independently of any exported module.
"""
import base64
import io
import re
import zipfile
from xml.sax.saxutils import escape

from odoo import api, fields, models
from odoo.exceptions import UserError

# Fields that MAY be set on a Studio Pro-generated ir.actions.server, and how to serialize each
# kind (see studio_server_action.py / studio_automation.py for exactly which combinations Studio
# Pro itself produces — this mirrors that surface, not the full ir.actions.server field set).
_ACTION_CHAR_FIELDS = ('update_path', 'evaluation_type', 'update_boolean_value', 'value',
                       'webhook_url', 'mail_post_method', 'resource_ref')
_ACTION_CODE_FIELDS = ('code',)
_ACTION_M2O_FIELDS = ('crud_model_id', 'link_field_id', 'template_id', 'selection_value')
_ACTION_M2M_FIELDS = ('webhook_field_ids',)


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
    # generic xmlid helper — works for ANY record of ANY model, assigning
    # one on the fly if it doesn't have one yet (mail templates, groups
    # created ad hoc, etc.)
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

    def _ref_for(self, record):
        return self._xmlid_for(record, '%s_%d' % (record._name.replace('.', '_'), record.id))

    def _is_studio_owned(self, record):
        """True if ``record`` was created by Studio Pro (or a previous export of this same
        App), false if it's a genuine pre-existing record from another installed addon.

        This matters because Studio Pro can edit NATIVE models (``res.partner``,
        ``sale.order``...), and a naive "every view/action/rule for this model" search would
        then also match hundreds of unrelated views/actions from whatever addons are installed
        — this filter is what keeps the export scoped to only what was actually built here.
        """
        existing = self.env['ir.model.data'].sudo().search(
            [('model', '=', record._name), ('res_id', '=', record.id)], limit=1)
        if not existing:
            return True  # no xmlid yet at all -> can only be something created at runtime
        return existing.module == 'studio_pro' or existing.module.startswith('studio_export_')

    # ------------------------------------------------------------------
    def action_generate(self):
        self.ensure_one()
        if not self.module_name:
            raise UserError(self.env._("Indica un nombre técnico para el módulo exportado."))
        app = self.app_id
        if not app.model_ids:
            raise UserError(self.env._("Esta app todavía no tiene modelos para exportar."))

        model_blocks, view_blocks = [], []
        security_blocks, access_rows = [], []
        automation_blocks, server_action_blocks, report_blocks = [], [], []
        hook_lines = []

        for model in app.model_ids:
            model_blocks.append(self._export_model(model))
        for model in app.model_ids:
            for field in model.field_id.filtered(lambda f: f.state == 'manual' and f.name != 'x_name'):
                model_blocks.append(self._export_field(field))

        model_names = app.model_ids.mapped('model')

        views = self.env['ir.ui.view'].sudo().search(
            [('model', 'in', model_names), ('type', '!=', 'qweb')])
        views = views.filtered(self._is_studio_owned)
        for view in views:
            view_blocks.append(self._export_view(view))

        actions = self.env['ir.actions.act_window'].sudo().search([('res_model', 'in', model_names)])
        actions = actions.filtered(self._is_studio_owned)
        for action in actions:
            view_blocks.append(self._export_action(action))

        menus = self.env['ir.ui.menu'].sudo().search([('id', 'child_of', app.menu_id.id)]) if app.menu_id \
            else self.env['ir.ui.menu'].sudo().browse()
        for menu in menus:
            view_blocks.append(self._export_menu(menu, actions))

        groups = app.manager_group_id + app.user_group_id
        for group in groups:
            security_blocks.append(self._export_group(group))

        accesses = self.env['ir.model.access'].sudo().search([('group_id', 'in', groups.ids)])
        for access in accesses:
            access_rows.append(self._export_access_row(access))

        rules = self.env['ir.rule'].sudo().search([('model_id.model', 'in', model_names)])
        rules = rules.filtered(self._is_studio_owned)
        for rule in rules:
            security_blocks.append(self._export_rule(rule))

        constraints = self.env['studio.model.constraint'].sudo().search(
            [('model_id', 'in', app.model_ids.ids), ('state', '=', 'applied')])
        for constraint in constraints:
            hook_lines.append(self._export_constraint_hook(constraint))

        flows = self.env['studio.automation.flow'].sudo().search(
            [('model_id', 'in', app.model_ids.ids), ('automation_id', '!=', False)])
        for flow in flows:
            automation_blocks.append(self._export_automation(flow))

        server_actions = self.env['studio.server.action'].sudo().search(
            [('model_id', 'in', app.model_ids.ids), ('action_server_id', '!=', False)])
        for sa in server_actions:
            server_action_blocks.append(self._export_server_action_record(sa.action_server_id))
            if sa.cron_id:
                server_action_blocks.append(self._export_cron(sa.cron_id, sa.action_server_id))

        reports = self.env['studio.report.builder'].sudo().search(
            [('model_id', 'in', app.model_ids.ids), ('state', '=', 'generated')])
        for report in reports:
            if report.report_view_id:
                report_blocks.append(self._export_view(report.report_view_id))
            if report.report_action_id:
                report_blocks.append(self._export_report_action(report.report_action_id))

        extra_data_files = []
        if automation_blocks:
            extra_data_files.append('data/automations.xml')
        if server_action_blocks:
            extra_data_files.append('data/server_actions.xml')
        if report_blocks:
            extra_data_files.append('data/reports.xml')

        files = {
            '%s/__init__.py' % self.module_name: self._build_init(bool(hook_lines)),
            '%s/__manifest__.py' % self.module_name: self._build_manifest(hook_lines, report_blocks, extra_data_files),
            '%s/data/models.xml' % self.module_name: self._wrap_odoo(model_blocks),
            '%s/views/views.xml' % self.module_name: self._wrap_odoo(view_blocks),
            '%s/security/security.xml' % self.module_name: self._wrap_odoo(security_blocks),
            '%s/security/ir.model.access.csv' % self.module_name: self._build_access_csv(access_rows),
        }
        if hook_lines:
            files['%s/hooks.py' % self.module_name] = self._build_hooks(hook_lines)
        if automation_blocks:
            files['%s/data/automations.xml' % self.module_name] = self._wrap_odoo(automation_blocks)
        if server_action_blocks:
            files['%s/data/server_actions.xml' % self.module_name] = self._wrap_odoo(server_action_blocks)
        if report_blocks:
            files['%s/data/reports.xml' % self.module_name] = self._wrap_odoo(report_blocks)

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for path, content in files.items():
                zf.writestr(path, content)

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

    def _wrap_odoo(self, blocks):
        return '<?xml version="1.0" encoding="utf-8"?>\n<odoo noupdate="1">\n%s\n</odoo>\n' % "\n".join(blocks)

    def _build_init(self, has_hooks):
        return "from . import hooks\n" if has_hooks else ""

    def _build_manifest(self, hook_lines, report_blocks, extra_data_files):
        # Order matters here: ir.rule / ir.model.access reference models, and views reference
        # models+fields, so data/models.xml must load first — otherwise a fresh install of the
        # exported module would fail on an unresolved ref() to a model that doesn't exist yet.
        data_files = ['data/models.xml', 'security/security.xml', 'security/ir.model.access.csv',
                      'views/views.xml'] + extra_data_files
        depends = ['base', 'mail', 'base_automation']
        if report_blocks:
            depends.append('web')
        lines = [
            "{",
            "    'name': %r," % self.app_id.name,
            "    'version': '18.0.1.0.0',",
            "    'category': 'Customizations',",
            "    'summary': 'Exportado desde Studio Pro',",
            "    'depends': %r," % depends,
            "    'data': %r," % data_files,
        ]
        if hook_lines:
            lines.append("    'post_init_hook': 'post_init_hook',")
        lines += ["    'installable': True,", "    'license': 'LGPL-3',", "}", ""]
        return "\n".join(lines)

    def _build_hooks(self, hook_lines):
        body = "\n".join(hook_lines) or "    pass"
        return (
            "# -*- coding: utf-8 -*-\n"
            "def post_init_hook(env):\n"
            "    \"\"\"Re-applies the database constraints Studio Pro had added live — a fresh\n"
            "    install of this exported module has no way to run raw SQL through XML data\n"
            "    files, so it happens here once, right after install.\"\"\"\n"
            "    cr = env.cr\n"
            "%s\n"
        ) % body

    def _build_access_csv(self, rows):
        header = "id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink\n"
        return header + "\n".join(rows) + ("\n" if rows else "")

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
        if field.index:
            lines.append('    <field name="index" eval="True"/>')
        if field.relation:
            lines.append('    <field name="relation">%s</field>' % esc(field.relation))
        if field.relation_field:
            lines.append('    <field name="relation_field">%s</field>' % esc(field.relation_field))
        if field.ttype == 'many2one' and field.on_delete:
            lines.append('    <field name="on_delete">%s</field>' % esc(field.on_delete))
        if field.compute:
            lines.append('    <field name="compute">%s</field>' % esc(field.compute))
            lines.append('    <field name="depends">%s</field>' % esc(field.depends or ''))
            lines.append('    <field name="store" eval="%s"/>' % bool(field.store))
            lines.append('    <field name="readonly" eval="True"/>')
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
        xmlid = self._xmlid_for(view, 'view_%s_%s' % ((view.model or 'qweb').replace('.', '_'), view.type))
        lines = [
            '  <record id="%s" model="ir.ui.view">' % xmlid.split('.', 1)[1],
            '    <field name="name">%s</field>' % esc(view.name),
        ]
        if view.model:
            lines.append('    <field name="model">%s</field>' % esc(view.model))
        lines.append('    <field name="type">%s</field>' % esc(view.type))
        if view.inherit_id:
            lines.append('    <field name="inherit_id" ref="%s"/>' % self._ref_for(view.inherit_id))
        if view.key:
            lines.append('    <field name="key">%s</field>' % esc(view.key))
        lines.append('    <field name="arch" type="xml">%s</field>' % (view.arch or ''))
        lines.append('  </record>')
        return "\n".join(lines)

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

    def _export_access_row(self, access):
        xmlid = self._xmlid_for(access, 'access_%s' % access.id)
        model_xmlid = self._xmlid_for(access.model_id, 'model_%s' % access.model_id.model.replace('.', '_'))
        group_xmlid = self._xmlid_for(access.group_id, 'group_%s' % access.group_id.id)
        return ','.join([
            xmlid.split('.', 1)[1], access.name or xmlid.split('.', 1)[1], model_xmlid, group_xmlid,
            str(int(access.perm_read)), str(int(access.perm_write)),
            str(int(access.perm_create)), str(int(access.perm_unlink)),
        ])

    def _export_rule(self, rule):
        xmlid = self._xmlid_for(rule, 'rule_%s' % rule.id)
        model_xmlid = self._xmlid_for(rule.model_id, 'model_%s' % rule.model_id.model.replace('.', '_'))
        lines = [
            '  <record id="%s" model="ir.rule">' % xmlid.split('.', 1)[1],
            '    <field name="name">%s</field>' % esc(rule.name),
            '    <field name="model_id" ref="%s"/>' % model_xmlid,
            '    <field name="domain_force">%s</field>' % esc(rule.domain_force or '[]'),
            '    <field name="perm_read" eval="%s"/>' % bool(rule.perm_read),
            '    <field name="perm_write" eval="%s"/>' % bool(rule.perm_write),
            '    <field name="perm_create" eval="%s"/>' % bool(rule.perm_create),
            '    <field name="perm_unlink" eval="%s"/>' % bool(rule.perm_unlink),
        ]
        if rule.groups:
            group_refs = ", ".join("ref('%s')" % self._ref_for(g) for g in rule.groups)
            lines.append('    <field name="groups" eval="[(6, 0, [%s])]"/>' % group_refs)
        lines.append('  </record>')
        return "\n".join(lines)

    def _export_constraint_hook(self, constraint):
        table = constraint.model_id.model.replace('.', '_')
        query = 'ALTER TABLE "%s" ADD CONSTRAINT "%s" %s' % (
            table, constraint.sql_name, constraint._sql_definition())
        return "    cr.execute(%r)" % query

    # ------------------------------------------------------------------
    # automations / server actions / crons / reports
    # ------------------------------------------------------------------
    def _export_server_action_record(self, action):
        xmlid = self._xmlid_for(action, 'server_action_%s' % action.id)
        model_xmlid = self._xmlid_for(action.model_id, 'model_%s' % action.model_id.model.replace('.', '_'))
        lines = [
            '  <record id="%s" model="ir.actions.server">' % xmlid.split('.', 1)[1],
            '    <field name="name">%s</field>' % esc(action.name),
            '    <field name="model_id" ref="%s"/>' % model_xmlid,
            '    <field name="state">%s</field>' % esc(action.state),
        ]
        for fname in _ACTION_CHAR_FIELDS + _ACTION_CODE_FIELDS:
            value = action[fname]
            if value:
                lines.append('    <field name="%s">%s</field>' % (fname, esc(value)))
        for fname in _ACTION_M2O_FIELDS:
            record = action[fname]
            if record:
                lines.append('    <field name="%s" ref="%s"/>' % (fname, self._ref_for(record)))
        for fname in _ACTION_M2M_FIELDS:
            records = action[fname]
            if records:
                refs = ", ".join("ref('%s')" % self._ref_for(r) for r in records)
                lines.append('    <field name="%s" eval="[(6, 0, [%s])]"/>' % (fname, refs))
        lines.append('  </record>')
        return "\n".join(lines)

    def _export_automation(self, flow):
        """One single ``base.automation`` record, referencing its
        ``ir.actions.server`` steps via ``ref()`` — the step records are
        emitted first in the returned text so their xmlids already exist
        by the time this file is loaded top to bottom (Odoo data files
        resolve ``ref()`` against what has already been defined earlier in
        the same load pass).
        """
        automation = flow.automation_id
        xmlid = self._xmlid_for(automation, 'automation_%s' % automation.id)
        model_xmlid = self._xmlid_for(flow.model_id, 'model_%s' % flow.model_id.model.replace('.', '_'))

        action_blocks = [self._export_server_action_record(a) for a in flow.generated_action_ids]
        action_refs = [self._ref_for(a) for a in flow.generated_action_ids]

        lines = [
            '  <record id="%s" model="base.automation">' % xmlid.split('.', 1)[1],
            '    <field name="name">%s</field>' % esc(automation.name),
            '    <field name="model_id" ref="%s"/>' % model_xmlid,
            '    <field name="trigger">%s</field>' % esc(automation.trigger),
            '    <field name="active" eval="%s"/>' % bool(automation.active),
        ]
        if automation.filter_domain and automation.filter_domain != '[]':
            lines.append('    <field name="filter_domain">%s</field>' % esc(automation.filter_domain))
        if action_refs:
            refs = ", ".join("ref('%s')" % r for r in action_refs)
            lines.append('    <field name="action_server_ids" eval="[(6, 0, [%s])]"/>' % refs)
        lines.append('  </record>')
        return "\n".join(action_blocks + [''] + lines)

    def _export_cron(self, cron, action):
        """The live cron's own ``code`` hardcodes the numeric database id of
        its ``ir.actions.server`` (``browse(<id>).run()``) — meaningless on
        a fresh install of the exported module, where that id won't exist
        or won't point at the right record. Regenerated here to resolve the
        action through its exported xmlid instead, via ``env.ref()``.
        """
        xmlid = self._xmlid_for(cron, 'cron_%s' % cron.id)
        action_ref = self._ref_for(action)
        code = ("env.ref(%r).with_context(active_model=model._name, active_ids=[], "
                "active_id=False).run()") % action_ref
        return (
            '  <record id="%s" model="ir.cron">\n'
            '    <field name="name">%s</field>\n'
            '    <field name="model_id" ref="%s"/>\n'
            '    <field name="state">code</field>\n'
            '    <field name="code">%s</field>\n'
            '    <field name="interval_number">%s</field>\n'
            '    <field name="interval_type">%s</field>\n'
            '    <field name="active" eval="%s"/>\n'
            '  </record>'
        ) % (xmlid.split('.', 1)[1], esc(cron.name), self._ref_for(action.model_id),
             esc(code), cron.interval_number, esc(cron.interval_type), bool(cron.active))

    def _export_report_action(self, report_action):
        xmlid = self._xmlid_for(report_action, 'report_%s' % report_action.id)
        lines = [
            '  <record id="%s" model="ir.actions.report">' % xmlid.split('.', 1)[1],
            '    <field name="name">%s</field>' % esc(report_action.name),
            '    <field name="model">%s</field>' % esc(report_action.model),
            '    <field name="report_type">%s</field>' % esc(report_action.report_type or 'qweb-pdf'),
            '    <field name="report_name">%s</field>' % esc(report_action.report_name),
            '    <field name="print_report_name">%s</field>' % esc(report_action.print_report_name or ''),
        ]
        if report_action.binding_model_id:
            lines.append('    <field name="binding_model_id" ref="%s"/>' % self._ref_for(report_action.binding_model_id))
        lines.append('  </record>')
        return "\n".join(lines)
