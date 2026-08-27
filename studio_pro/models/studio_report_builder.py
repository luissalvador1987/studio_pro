# -*- coding: utf-8 -*-
import re

from odoo import api, fields, models
from odoo.exceptions import UserError


class StudioReportBuilder(models.Model):
    _name = 'studio.report.builder'
    _description = 'Constructor de Reportes de Studio Pro'
    _order = 'name'

    name = fields.Char(string="Nombre", required=True)
    app_id = fields.Many2one('studio.app', string="App", ondelete='cascade')
    model_id = fields.Many2one('ir.model', string="Modelo", required=True, ondelete='cascade')
    model_name = fields.Char(related='model_id.model', store=True, readonly=True)
    title = fields.Char(string="Título", help="Título impreso en la parte superior del reporte.", required=True)
    field_ids = fields.Many2many('ir.model.fields', string="Columnas",
                                  domain="[('model_id', '=', model_id), ('store', '=', True)]", required=True)
    group_by_field_id = fields.Many2one('ir.model.fields', string="Agrupar por",
                                         domain="[('model_id', '=', model_id)]")
    orientation = fields.Selection([('portrait', 'Vertical'), ('landscape', 'Horizontal')],
                                    string="Orientación", default='portrait')

    report_action_id = fields.Many2one('ir.actions.report', string="Acción de reporte", readonly=True, copy=False)
    report_view_id = fields.Many2one('ir.ui.view', string="Vista del reporte", readonly=True, copy=False)
    state = fields.Selection([('draft', 'Borrador'), ('generated', 'Generado')],
                              string="Estado", default='draft', readonly=True, copy=False)

    def action_generate(self):
        for report in self:
            report._generate()
        return True

    def _report_key(self):
        self.ensure_one()
        slug = re.sub(r'[^a-z0-9]+', '_', self.name.strip().lower()).strip('_') or 'report'
        return 'studio_pro.studio_report_%s_%s' % (slug, self.id)

    def _build_qweb_arch(self):
        self.ensure_one()
        key = self._report_key()
        cols = self.field_ids
        ths = "".join('<th>%s</th>' % (f.field_description or f.name) for f in cols)

        def cell(f):
            widget = ' widget="many2one"' if f.ttype in ('many2one',) else ''
            return '<td><span t-field="line.%s"%s/></td>' % (f.name, widget)

        tds = "".join(cell(f) for f in cols)
        colspan = len(cols) or 1

        if self.group_by_field_id:
            gfield = self.group_by_field_id.name
            is_relational = self.group_by_field_id.ttype == 'many2one'
            group_label_expr = ("line.%s.display_name if line.%s else ''" % (gfield, gfield)) if is_relational \
                else ("line.%s or ''" % gfield)
            loop = (
                '<t t-set="studio_sorted_docs" t-value="docs.sorted(%r)"/>'
                '<t t-set="studio_prev_group" t-value="None"/>'
                '<table class="table table-sm o_table">'
                '<thead><tr>%s</tr></thead>'
                '<tbody>'
                '<t t-foreach="studio_sorted_docs" t-as="line" t-key="line.id">'
                '<tr t-if="line.%s != studio_prev_group">'
                '<td t-att-colspan="%d"><strong t-esc="%s"/></strong></td>'
                '</tr>'
                '<t t-set="studio_prev_group" t-value="line.%s"/>'
                '<tr>%s</tr>'
                '</t>'
                '</tbody>'
                '</table>'
            ) % (gfield, ths, gfield, colspan, group_label_expr, gfield, tds)
        else:
            loop = (
                '<table class="table table-sm o_table">'
                '<thead><tr>%s</tr></thead>'
                '<tbody>'
                '<t t-foreach="docs" t-as="line" t-key="line.id">'
                '<tr>%s</tr>'
                '</t>'
                '</tbody>'
                '</table>'
            ) % (ths, tds)

        return (
            '<t t-name="%s">'
            '<t t-call="web.html_container">'
            '<t t-call="web.internal_layout">'
            '<div class="page">'
            '<h2 t-esc="title or \'%s\'"/>'
            '%s'
            '</div>'
            '</t>'
            '</t>'
            '</t>'
        ) % (key, self.title.replace("'", "&#39;"), loop)

    def _generate(self):
        self.ensure_one()
        if not self.field_ids:
            raise UserError(self.env._("Elige al menos una columna antes de generar el reporte."))
        key = self._report_key()
        arch = self._build_qweb_arch()

        View = self.env['ir.ui.view'].sudo()
        if self.report_view_id:
            self.report_view_id.write({'arch': arch})
            view = self.report_view_id
        else:
            view = View.create({
                'name': key,
                'key': key,
                'type': 'qweb',
                'arch': arch,
                'model': self.model_id.model,
            })

        Report = self.env['ir.actions.report'].sudo()
        report_vals = {
            'name': self.title,
            'model': self.model_id.model,
            'report_type': 'qweb-pdf',
            'report_name': key,
            'print_report_name': "'%s'" % (self.title,),
            'studio_app_id': self.app_id.id,
        }
        if self.report_action_id:
            self.report_action_id.write(report_vals)
            action = self.report_action_id
        else:
            action = Report.create(report_vals)

        self.write({'report_view_id': view.id, 'report_action_id': action.id, 'state': 'generated'})
        self.env['studio.change'].log(
            'report', 'studio.report.builder', self.id, action='update',
            app_id=self.app_id.id, summary="Reporte '%s' generado" % self.name)
        return True

    def action_print(self):
        self.ensure_one()
        if not self.report_action_id:
            self.action_generate()
        records = self.env[self.model_id.model].sudo().search([], limit=200)
        return self.report_action_id.report_action(records)
