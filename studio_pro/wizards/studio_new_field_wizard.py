# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.studio_app import slugify_technical

FIELD_TYPES = [
    ('char', 'Texto'),
    ('text', 'Texto multilínea'),
    ('html', 'Texto enriquecido'),
    ('integer', 'Número'),
    ('float', 'Número decimal'),
    ('monetary', 'Monetario'),
    ('boolean', 'Casilla de verificación'),
    ('date', 'Fecha'),
    ('datetime', 'Fecha y hora'),
    ('selection', 'Selección'),
    ('many2one', 'Registro relacionado (Many2one)'),
    ('many2many', 'Varios registros relacionados (Many2many)'),
    ('one2many', 'Lista de registros relacionados (One2many)'),
    ('binary', 'Archivo'),
]

RELATIONAL_TYPES = ('many2one', 'many2many', 'one2many')


class StudioNewFieldWizard(models.TransientModel):
    _name = 'studio.new.field.wizard'
    _description = 'Studio Pro — Asistente de Nuevo Campo'

    res_model_id = fields.Many2one('ir.model', required=True, string="Modelo",
                                    help="Cualquier modelo, estándar o personalizado (ej: res.partner, x_equipo).")
    field_description = fields.Char(required=True, string="Etiqueta", help="Ej: 'Fecha de fin de garantía'")
    technical_name_preview = fields.Char(compute='_compute_technical_name_preview', string="Nombre técnico")
    ttype = fields.Selection(FIELD_TYPES, required=True, default='char', string="Tipo")
    required = fields.Boolean(string="Obligatorio")
    relation_model_id = fields.Many2one('ir.model', string="Modelo relacionado",
                                         help="Requerido para campos Many2one / Many2many / One2many.")
    relation_field_id = fields.Many2one('ir.model.fields', string="Campo relacionado (One2many)",
                                         domain="[('model_id', '=', relation_model_id), ('ttype', '=', 'many2one')]",
                                         help="El campo Many2one en el modelo relacionado que apunta de vuelta aquí.")
    selection_options = fields.Char(
        string="Opciones", help="Pares 'valor:Etiqueta' separados por comas, ej: 'nuevo:Nuevo,hecho:Hecho'.")

    target_view_id = fields.Many2one('ir.ui.view', string="Agregar a la vista",
                                      domain="[('model', '=', res_model_name), ('type', 'in', ('form', 'list'))]")
    res_model_name = fields.Char(related='res_model_id.model')

    @api.depends('field_description')
    def _compute_technical_name_preview(self):
        for wiz in self:
            wiz.technical_name_preview = slugify_technical(wiz.field_description, prefix='x_studio_') if wiz.field_description else ''

    def _parse_selection_options(self):
        options = []
        for chunk in (self.selection_options or '').split(','):
            chunk = chunk.strip()
            if not chunk:
                continue
            if ':' in chunk:
                value, label = chunk.split(':', 1)
            else:
                value = label = chunk
            options.append((value.strip(), label.strip()))
        return options

    def action_create_field(self):
        self.ensure_one()
        if self.ttype in RELATIONAL_TYPES and not self.relation_model_id:
            raise UserError(self.env._("Elige un modelo relacionado para este tipo de campo."))
        if self.ttype == 'one2many' and not self.relation_field_id:
            raise UserError(self.env._("Elige el campo Many2one del modelo relacionado que apunta de vuelta aquí."))

        name = slugify_technical(self.field_description, prefix='x_studio_')
        if self.env['ir.model.fields'].sudo().search_count(
                [('model_id', '=', self.res_model_id.id), ('name', '=', name)]):
            raise UserError(self.env._("El campo '%s' ya existe en este modelo.") % name)

        vals = {
            'model_id': self.res_model_id.id,
            'name': name,
            'field_description': self.field_description,
            'ttype': self.ttype,
            'required': self.required,
            'state': 'manual',
        }
        if self.ttype in RELATIONAL_TYPES:
            vals['relation'] = self.relation_model_id.model
        if self.ttype == 'one2many':
            vals['relation_field'] = self.relation_field_id.name
        if self.ttype == 'selection':
            options = self._parse_selection_options()
            if not options:
                raise UserError(self.env._("Indica al menos una opción, ej: 'nuevo:Nuevo,hecho:Hecho'."))
            vals['selection_ids'] = [(0, 0, {'value': v, 'name': l, 'sequence': i})
                                      for i, (v, l) in enumerate(options)]

        field = self.env['ir.model.fields'].sudo().create(vals)

        if self.target_view_id:
            self.target_view_id.sudo().studio_insert_field(name)

        self.env['studio.change'].log(
            'field', 'ir.model.fields', field.id, action='create',
            app_id=self.res_model_id.studio_app_id.id,
            summary="Campo '%s' (%s) agregado en %s" % (self.field_description, name, self.res_model_id.model))

        return {'type': 'ir.actions.act_window_close'}
