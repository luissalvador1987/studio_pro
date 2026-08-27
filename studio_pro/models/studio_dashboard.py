# -*- coding: utf-8 -*-
"""Dashboards: graph/pivot/kanban/list views over any model — standard base or
custom, from any addon — built entirely on the safe, access-controlled Odoo
ORM (read_group / search_read), the same mechanism Odoo's own Reporting/BI
screens use. This is deliberately *not* a raw SQL query tool: letting Studio
Pro users run arbitrary SQL would bypass every access right and business
rule in the database and is a real security risk, not something Odoo Studio
itself offers either. Ask a database administrator directly if you truly
need ad-hoc SQL.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError


class StudioDashboard(models.Model):
    _name = 'studio.dashboard'
    _description = 'Tablero de Studio Pro'
    _order = 'name'

    name = fields.Char(string="Nombre", required=True)
    app_id = fields.Many2one('studio.app', string="App", ondelete='cascade')
    model_id = fields.Many2one('ir.model', string="Modelo", required=True, ondelete='cascade',
                                help="Cualquier modelo: estándar, de otro addon, o creado con Studio Pro.")
    model_name = fields.Char(related='model_id.model', store=True, readonly=True)
    domain = fields.Char(string="Dominio", default='[]', help="Filtro aplicado a los datos del tablero.")

    has_graph = fields.Boolean(string="Gráfico", default=True)
    graph_type = fields.Selection([('bar', 'Barras'), ('line', 'Líneas'), ('pie', 'Circular')],
                                   string="Tipo de gráfico", default='bar')
    has_pivot = fields.Boolean(string="Tabla dinámica", default=True)
    has_list = fields.Boolean(string="Lista", default=True)
    has_kanban = fields.Boolean(string="Kanban", default=False)

    measure_field_id = fields.Many2one('ir.model.fields', string="Medida",
                                        domain="[('model_id', '=', model_id), "
                                                "('ttype', 'in', ('integer', 'float', 'monetary'))]",
                                        help="Campo numérico a medir/sumar (opcional).")
    groupby_field_id = fields.Many2one('ir.model.fields', string="Agrupar por",
                                        domain="[('model_id', '=', model_id)]")

    action_id = fields.Many2one('ir.actions.act_window', string="Acción", readonly=True, copy=False)
    menu_id = fields.Many2one('ir.ui.menu', string="Menú", readonly=True, copy=False)
    state = fields.Selection([('draft', 'Borrador'), ('generated', 'Generado')],
                              string="Estado", default='draft', readonly=True, copy=False)

    def _view_mode(self):
        self.ensure_one()
        modes = []
        if self.has_graph:
            modes.append('graph')
        if self.has_pivot:
            modes.append('pivot')
        if self.has_kanban:
            modes.append('kanban')
        if self.has_list:
            modes.append('list')
        return ','.join(modes) or 'list'

    def action_generate(self):
        for dashboard in self:
            dashboard._generate()
        return True

    def _generate(self):
        self.ensure_one()
        if not (self.has_graph or self.has_pivot or self.has_list or self.has_kanban):
            raise UserError(self.env._("Activa al menos un tipo de vista (Gráfico, Tabla dinámica, Lista o Kanban)."))
        try:
            import ast
            ast.literal_eval(self.domain or '[]')
        except (ValueError, SyntaxError) as e:
            raise UserError(self.env._("El dominio no es válido: %s") % e)

        context = {'search_default_filter': 1}
        if self.measure_field_id:
            context['graph_measure'] = self.measure_field_id.name
            context['pivot_measures'] = [self.measure_field_id.name]
        if self.groupby_field_id:
            context['graph_groupbys'] = [self.groupby_field_id.name]
            context['pivot_row_groupby'] = [self.groupby_field_id.name]
            context['search_default_groupby_studio'] = 1

        Action = self.env['ir.actions.act_window'].sudo()
        action_vals = {
            'name': self.name,
            'res_model': self.model_id.model,
            'view_mode': self._view_mode(),
            'domain': self.domain or '[]',
            'context': str(context),
        }
        if self.action_id:
            self.action_id.write(action_vals)
            action = self.action_id
        else:
            action = Action.create(action_vals)

        Menu = self.env['ir.ui.menu'].sudo()
        if not self.menu_id:
            self.menu_id = Menu.create({
                'name': self.name,
                'parent_id': self.app_id.menu_id.id if self.app_id and self.app_id.menu_id else False,
                'action': 'ir.actions.act_window,%d' % action.id,
            })
        else:
            self.menu_id.write({'name': self.name})

        self.write({'action_id': action.id, 'state': 'generated'})
        self.env['studio.change'].log(
            'report', 'studio.dashboard', self.id, action='update',
            app_id=self.app_id.id, summary="Tablero '%s' generado" % self.name)
        return True

    def action_open(self):
        self.ensure_one()
        if not self.action_id:
            self.action_generate()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': self.model_id.model,
            'view_mode': self._view_mode(),
            'domain': self.action_id.domain,
            'context': self.action_id.context,
        }
