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

ON_DELETE_SELECTION = [
    ('set null', "Dejar en blanco (set null)"),
    ('restrict', "Impedir borrar el registro relacionado (restrict)"),
    ('cascade', "Borrar en cascada (cascade)"),
]

DEFAULT_COMPUTE_CODE = (
    "# Se ejecuta sobre el recordset 'self'; asigna el valor con record['%s'] = ....\n"
    "# Módulos disponibles: time, datetime, dateutil.\n"
    "for record in self:\n"
    "    record['%s'] = False\n"
)


class StudioNewFieldWizard(models.TransientModel):
    _name = 'studio.new.field.wizard'
    _description = 'Studio Pro — Asistente de Nuevo Campo'

    res_model_id = fields.Many2one('ir.model', required=True, string="Modelo",
                                    help="Cualquier modelo, estándar o personalizado (ej: res.partner, x_equipo).")
    field_description = fields.Char(required=True, string="Etiqueta", help="Ej: 'Fecha de fin de garantía'")
    technical_name_preview = fields.Char(compute='_compute_technical_name_preview', string="Nombre técnico")
    ttype = fields.Selection(FIELD_TYPES, required=True, default='char', string="Tipo")
    required = fields.Boolean(string="Obligatorio")
    index = fields.Boolean(
        string="Indexado", help="Crea un índice de base de datos — acelera búsquedas/filtros por este campo.")
    relation_model_id = fields.Many2one('ir.model', string="Modelo relacionado",
                                         help="Requerido para campos Many2one / Many2many / One2many.")
    relation_field_id = fields.Many2one('ir.model.fields', string="Campo relacionado (One2many)",
                                         domain="[('model_id', '=', relation_model_id), ('ttype', '=', 'many2one')]",
                                         help="El campo Many2one en el modelo relacionado que apunta de vuelta aquí.")
    on_delete = fields.Selection(
        ON_DELETE_SELECTION, string="Al borrar el registro relacionado", default='set null',
        help="Solo aplica a Many2one: qué pasa con este registro si el registro que apunta se borra.")
    selection_options = fields.Char(
        string="Opciones", help="Pares 'valor:Etiqueta' separados por comas, ej: 'nuevo:Nuevo,hecho:Hecho'.")

    is_computed = fields.Boolean(
        string="Es un campo calculado", help="Su valor se calcula con código Python en vez de escribirse a mano.")
    compute_code = fields.Text(
        string="Código de cálculo", default=lambda self: DEFAULT_COMPUTE_CODE % ('x', 'x'),
        help="Recorre 'self' y asigna record['nombre_del_campo'] = .... Mismo motor sandboxeado que las "
             "Funciones/Automatizaciones — no es una consola de Python libre.")
    compute_depends = fields.Char(
        string="Depende de", help="Campos separados por comas de los que depende el cálculo, ej: 'qty,price_unit' "
                                   "— equivale al decorador @api.depends. Se recalcula solo cuando estos cambian.")
    store = fields.Boolean(
        string="Guardar en base de datos", default=True,
        help="Si se desmarca (solo campos calculados), el valor se recalcula cada vez que se lee y no ocupa "
             "columna en la base de datos ni se puede usar para filtrar/agrupar.")

    restrict_group_ids = fields.Many2many(
        'res.groups', string="Restringir a estos grupos",
        help="Si se indica, el campo solo será visible (en la vista elegida abajo) para estos grupos — la "
             "manera real en que Odoo hace seguridad de campo para campos creados en tiempo de ejecución.")
    target_view_id = fields.Many2one('ir.ui.view', string="Agregar a la vista",
                                      domain="[('model', '=', res_model_name), ('type', 'in', ('form', 'list'))]")
    res_model_name = fields.Char(related='res_model_id.model')

    @api.depends('field_description')
    def _compute_technical_name_preview(self):
        for wiz in self:
            wiz.technical_name_preview = slugify_technical(wiz.field_description, prefix='x_studio_') if wiz.field_description else ''

    @api.onchange('field_description')
    def _onchange_field_description_compute_default(self):
        for wiz in self:
            if wiz.is_computed:
                name = slugify_technical(wiz.field_description, prefix='x_studio_') or 'x'
                wiz.compute_code = DEFAULT_COMPUTE_CODE % (name, name)

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
        if self.is_computed and not (self.compute_code or '').strip():
            raise UserError(self.env._("Escribe el código de cálculo, o desmarca 'Es un campo calculado'."))
        if self.is_computed and self.ttype in ('many2many', 'one2many'):
            raise UserError(
                self.env._("Los campos calculados de Studio Pro no admiten Many2many/One2many todavía; "
                            "usa una Función (Acción de Servidor) para esa lógica."))

        name = slugify_technical(self.field_description, prefix='x_studio_')
        if self.env['ir.model.fields'].sudo().search_count(
                [('model_id', '=', self.res_model_id.id), ('name', '=', name)]):
            raise UserError(self.env._("El campo '%s' ya existe en este modelo.") % name)

        vals = {
            'model_id': self.res_model_id.id,
            'name': name,
            'field_description': self.field_description,
            'ttype': self.ttype,
            'required': self.required and not self.is_computed,
            'index': self.index,
            'state': 'manual',
        }
        if self.ttype in RELATIONAL_TYPES:
            vals['relation'] = self.relation_model_id.model
        if self.ttype == 'one2many':
            vals['relation_field'] = self.relation_field_id.name
        if self.ttype == 'many2one':
            vals['on_delete'] = self.on_delete
        if self.ttype == 'selection':
            options = self._parse_selection_options()
            if not options:
                raise UserError(self.env._("Indica al menos una opción, ej: 'nuevo:Nuevo,hecho:Hecho'."))
            vals['selection_ids'] = [(0, 0, {'value': v, 'name': l, 'sequence': i})
                                      for i, (v, l) in enumerate(options)]
        if self.is_computed:
            vals['compute'] = self.compute_code
            vals['depends'] = self.compute_depends or ''
            vals['store'] = self.store
            vals['readonly'] = True

        field = self.env['ir.model.fields'].sudo().create(vals)

        if self.target_view_id:
            groups = self._restrict_group_xmlids()
            self.target_view_id.sudo().studio_insert_field(name, groups=groups)

        self.env['studio.change'].log(
            'field', 'ir.model.fields', field.id, action='create',
            app_id=self.res_model_id.studio_app_id.id,
            summary="Campo '%s' (%s) agregado en %s" % (self.field_description, name, self.res_model_id.model))

        return {'type': 'ir.actions.act_window_close'}

    def _restrict_group_xmlids(self):
        """``groups="..."`` on a view node needs external ids, not raw group
        ids — ``ir.model.data`` may not have one for a group created ad hoc
        (e.g. by another Studio Pro screen) with no xmlid, so fall back to
        assigning one on the fly (same trick Odoo's own view editor uses).
        """
        if not self.restrict_group_ids:
            return False
        xmlids = []
        for group in self.restrict_group_ids:
            xmlid = group.get_external_id().get(group.id)
            if not xmlid:
                xmlid = 'studio_pro.studio_autogroup_%d' % group.id
                self.env['ir.model.data'].sudo().create({
                    'name': 'studio_autogroup_%d' % group.id, 'module': 'studio_pro',
                    'model': 'res.groups', 'res_id': group.id, 'noupdate': True,
                })
            xmlids.append(xmlid)
        return ','.join(xmlids)
