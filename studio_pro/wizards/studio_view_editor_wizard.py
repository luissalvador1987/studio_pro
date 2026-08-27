# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class StudioViewEditorWizard(models.TransientModel):
    _name = 'studio.view.editor.wizard'
    _description = 'Studio Pro — Editor de Vistas'

    view_id = fields.Many2one('ir.ui.view', string="Vista", required=True)
    model_name = fields.Char(related='view_id.model', readonly=True)
    view_type = fields.Selection(related='view_id.type', readonly=True)
    line_ids = fields.One2many('studio.view.editor.line', 'wizard_id', string="Campos")
    add_field_id = fields.Many2one('ir.model.fields', string="Campo a agregar")

    new_group_title = fields.Char(string="Título del nuevo grupo")
    new_page_title = fields.Char(string="Título de la nueva pestaña")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        view_id = res.get('view_id') or self.env.context.get('default_view_id')
        if view_id and 'line_ids' in fields_list:
            res['line_ids'] = self._build_line_commands(view_id)
        return res

    def _build_line_commands(self, view_id):
        view = self.env['ir.ui.view'].sudo().browse(view_id)
        lines = view.studio_get_field_lines()
        return [(0, 0, {
            'sequence': i * 10,
            'xpath': l['xpath'],
            'parent_xpath': l['parent_xpath'],
            'field_name': l['name'],
            'label': l['string'],
            'ttype': l['ttype'],
            'required': l['required'],
            'readonly': l['readonly'],
            'invisible': l['invisible'],
        }) for i, l in enumerate(lines)]

    def action_add_field(self):
        self.ensure_one()
        if not self.add_field_id:
            raise UserError(self.env._("Primero elige un campo para agregar."))
        if self.add_field_id.name in self.line_ids.mapped('field_name'):
            raise UserError(self.env._("Este campo ya está en la vista."))
        last_parent = self.line_ids[-1:].parent_xpath if self.line_ids else False
        next_seq = (max(self.line_ids.mapped('sequence')) + 10) if self.line_ids else 0
        self.line_ids = [(0, 0, {
            'sequence': next_seq,
            'xpath': False,
            'parent_xpath': last_parent or '',
            'field_name': self.add_field_id.name,
            'label': self.add_field_id.field_description,
            'ttype': self.add_field_id.ttype,
        })]
        self.add_field_id = False
        return True

    def action_add_group(self):
        self.ensure_one()
        self.view_id.sudo().studio_add_group(string=self.new_group_title or False)
        self.new_group_title = False
        return True

    def action_add_page(self):
        self.ensure_one()
        if not self.new_page_title:
            raise UserError(self.env._("Escribe un título para la nueva pestaña."))
        self.view_id.sudo().studio_add_page(self.new_page_title)
        self.new_page_title = False
        return True

    def action_apply(self):
        self.ensure_one()
        lines = [{
            'xpath': line.xpath,
            'parent_xpath': line.parent_xpath,
            'name': line.field_name,
            'required': line.required,
            'readonly': line.readonly,
            'invisible': line.invisible,
        } for line in self.line_ids.sorted('sequence')]
        self.view_id.sudo().studio_apply_field_lines(lines)
        self.env['studio.change'].log(
            'view', 'ir.ui.view', self.view_id.id, action='update',
            summary="Diseño de la vista #%s (%s) editado" % (self.view_id.id, self.view_id.model))
        return {'type': 'ir.actions.act_window_close'}


class StudioViewEditorLine(models.TransientModel):
    _name = 'studio.view.editor.line'
    _description = 'Studio Pro — Línea del Editor de Vistas'
    _order = 'sequence, id'

    wizard_id = fields.Many2one('studio.view.editor.wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    xpath = fields.Char()
    parent_xpath = fields.Selection(selection='_selection_parent_xpath', string="Ubicación", default='')
    field_name = fields.Char(string="Campo", required=True)
    label = fields.Char(string="Etiqueta")
    ttype = fields.Char(string="Tipo")
    required = fields.Boolean(string="Obligatorio")
    readonly = fields.Boolean(string="Solo lectura")
    invisible = fields.Boolean(string="Invisible")

    def _selection_parent_xpath(self):
        wizard = self.wizard_id
        if not wizard:
            wizard_id = self.env.context.get('default_wizard_id')
            wizard = self.env['studio.view.editor.wizard'].browse(wizard_id) if wizard_id else None
        if not wizard or not wizard.view_id:
            return [('', '(Nivel principal)')]
        containers = wizard.view_id.sudo().studio_get_containers()
        return [(c['xpath'], c['label']) for c in containers]
