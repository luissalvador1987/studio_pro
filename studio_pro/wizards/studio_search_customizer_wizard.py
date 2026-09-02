# -*- coding: utf-8 -*-
"""Agrega filtros y 'Agrupar por' guiados (sin XML) a la vista de búsqueda
de cualquier modelo — la contraparte no-código de lo que
studio.view.inherit.wizard ya permite hacer a mano con xpath."""
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models.studio_app import slugify_technical

FILTER_OPERATORS = [
    ('=', "Es igual a"), ('!=', "Es distinto de"),
    ('>', "Mayor que"), ('<', "Menor que"),
    ('>=', "Mayor o igual que"), ('<=', "Menor o igual que"),
    ('like', "Contiene"), ('not like', "No contiene"),
    ('is_true', "Es verdadero"), ('is_false', "Es falso"),
    ('is_set', "Tiene un valor"), ('is_not_set', "Está vacío"),
]
_VALUELESS_OPERATORS = {'is_true', 'is_false', 'is_set', 'is_not_set'}


class StudioSearchFilterLine(models.TransientModel):
    _name = 'studio.search.filter.line'
    _description = 'Studio Pro — Línea de filtro de búsqueda'

    wizard_id = fields.Many2one('studio.search.customizer.wizard', ondelete='cascade')
    sequence = fields.Integer(default=10)
    label = fields.Char(required=True, string="Etiqueta del filtro", help="Ej: 'Solo vencidas'")
    res_model_id = fields.Many2one(related='wizard_id.res_model_id')
    field_id = fields.Many2one('ir.model.fields', required=True, string="Campo",
                                domain="[('model_id', '=', res_model_id)]")
    operator = fields.Selection(FILTER_OPERATORS, required=True, default='=')
    value = fields.Char(string="Valor", help="No aplica para 'Es verdadero/falso' ni 'Tiene/no tiene valor'.")

    def build_domain(self):
        self.ensure_one()
        fname = self.field_id.name
        if self.operator == 'is_true':
            return "[('%s', '=', True)]" % fname
        if self.operator == 'is_false':
            return "[('%s', '=', False)]" % fname
        if self.operator == 'is_set':
            return "[('%s', '!=', False)]" % fname
        if self.operator == 'is_not_set':
            return "[('%s', '=', False)]" % fname
        raw = self.value or ''
        if self.field_id.ttype in ('integer', 'float', 'monetary'):
            try:
                value_repr = repr(float(raw) if self.field_id.ttype != 'integer' else int(raw))
            except ValueError:
                raise UserError(_("'%s' necesita un valor numérico para el campo %s.") % (
                    self.label, self.field_id.field_description))
        else:
            value_repr = repr(raw)
        return "[('%s', '%s', %s)]" % (fname, self.operator, value_repr)


class StudioSearchGroupbyLine(models.TransientModel):
    _name = 'studio.search.groupby.line'
    _description = 'Studio Pro — Línea de agrupar-por de búsqueda'

    wizard_id = fields.Many2one('studio.search.customizer.wizard', ondelete='cascade')
    sequence = fields.Integer(default=10)
    res_model_id = fields.Many2one(related='wizard_id.res_model_id')
    field_id = fields.Many2one(
        'ir.model.fields', required=True, string="Campo",
        domain="[('model_id', '=', res_model_id), "
               "('ttype', 'in', ['many2one', 'selection', 'char', 'boolean', 'date', 'datetime'])]")
    label = fields.Char(string="Etiqueta (opcional)")


class StudioSearchCustomizerWizard(models.TransientModel):
    _name = 'studio.search.customizer.wizard'
    _description = 'Studio Pro — Personalizar Búsqueda'

    res_model_id = fields.Many2one('ir.model', string="Modelo", required=True,
                                    help="Cualquier modelo, estándar o de Studio Pro.")
    filter_line_ids = fields.One2many('studio.search.filter.line', 'wizard_id', string="Filtros")
    groupby_line_ids = fields.One2many('studio.search.groupby.line', 'wizard_id', string="Agrupar por")

    def _get_or_create_search_view(self):
        self.ensure_one()
        View = self.env['ir.ui.view'].sudo()
        view = View.search([('model', '=', self.res_model_id.model), ('type', '=', 'search')],
                            order='priority', limit=1)
        if view:
            return view
        return self.env['ir.model'].sudo().studio_create_view(self.res_model_id.model, 'search')

    def action_apply(self):
        self.ensure_one()
        if not self.filter_line_ids and not self.groupby_line_ids:
            raise UserError(_("Agregá al menos un filtro o un 'agrupar por'."))
        view = self._get_or_create_search_view()
        for line in self.filter_line_ids:
            name = 'studio_filter_%s' % slugify_technical(line.label, prefix='')
            view.studio_insert_filter(name=name, string=line.label, domain=line.build_domain())
        for line in self.groupby_line_ids:
            label = line.label or line.field_id.field_description
            name = 'studio_groupby_%s' % slugify_technical(label, prefix='')
            view.studio_insert_filter(
                name=name, string=label, context="{'group_by': '%s'}" % line.field_id.name)
        self.env['studio.change'].log(
            'view', 'ir.ui.view', view.id, action='update',
            app_id=self.res_model_id.studio_app_id.id,
            summary="Búsqueda de %s: %s filtro(s), %s agrupación(es)" % (
                self.res_model_id.model, len(self.filter_line_ids), len(self.groupby_line_ids)))
        return {
            'type': 'ir.actions.act_window', 'res_model': self.res_model_id.model,
            'view_mode': 'list,form', 'target': 'current',
        }
