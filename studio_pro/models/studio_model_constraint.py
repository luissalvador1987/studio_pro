# -*- coding: utf-8 -*-
"""Real PostgreSQL-level constraints (UNIQUE / CHECK) on Studio Pro-created
models — deliberately restricted to models with ``state == 'manual'``
(created through Studio Pro or Odoo's own technical "New Model" screen),
never on native Odoo models.

Why raw SQL is safe here, unlike an open SQL console (which Studio Pro
deliberately does not offer, see the module description): the SQL is
entirely templated from validated, structured inputs (a constraint name,
a list of already-existing field names, or a single free-form CHECK
expression) — never arbitrary user SQL statements — and only reachable by
the same System Administrator group that already has full field/model
creation power in this module. It is also safe to leave unmanaged by
Odoo's own registry: a 'manual' model has no real Python
``_sql_constraints`` class attribute for Odoo to reconcile against, so its
constraint-reconciliation logic never touches (and never drops) a
constraint added here.
"""
import re

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')


class StudioModelConstraint(models.Model):
    _name = 'studio.model.constraint'
    _description = 'Studio Pro — Restricción de base de datos'
    _order = 'model_id, name'

    model_id = fields.Many2one(
        'ir.model', string="Modelo", required=True, ondelete='cascade',
        domain=[('state', '=', 'manual')],
        help="Solo modelos creados con Studio Pro (o la pantalla técnica de Odoo) — nunca modelos "
             "nativos, para no arriesgar la integridad de tablas del núcleo.")
    model_name = fields.Char(related='model_id.model')
    name = fields.Char(
        string="Nombre técnico", required=True,
        help="Solo minúsculas, números y guion bajo, ej: 'uniq_code'.")
    constraint_type = fields.Selection([
        ('unique', "Único (UNIQUE)"), ('check', "Condición (CHECK)"),
    ], required=True, default='unique')
    field_ids = fields.Many2many(
        'ir.model.fields', string="Campos (para Único)",
        domain="[('model_id', '=', model_id)]")
    check_expression = fields.Char(
        string="Expresión (para Condición)",
        help="Expresión SQL booleana sobre columnas del propio modelo, ej: 'hour_from < hour_to'.")
    message = fields.Char(string="Mensaje de error", required=True)
    state = fields.Selection([('draft', "No aplicada"), ('applied', "Aplicada")],
                              default='draft', required=True, readonly=True, copy=False)
    sql_name = fields.Char(string="Nombre real en PostgreSQL", compute='_compute_sql_name')

    _sql_constraints = [
        ('name_uniq', "unique(model_id, name)", "Ya existe una restricción con ese nombre en este modelo."),
    ]

    @api.depends('model_id.model', 'name')
    def _compute_sql_name(self):
        for rec in self:
            table = (rec.model_id.model or '').replace('.', '_')
            rec.sql_name = '%s_studio_%s' % (table, rec.name) if table and rec.name else False

    @api.constrains('name')
    def _check_name(self):
        for rec in self:
            if not _NAME_RE.match(rec.name or ''):
                raise ValidationError(
                    "El nombre técnico debe empezar con una letra y solo contener minúsculas, "
                    "números y guion bajo.")

    @api.constrains('constraint_type', 'field_ids', 'check_expression')
    def _check_definition(self):
        for rec in self:
            if rec.constraint_type == 'unique' and not rec.field_ids:
                raise ValidationError("Elige al menos un campo para una restricción Única.")
            if rec.constraint_type == 'check' and not (rec.check_expression or '').strip():
                raise ValidationError("Escribe la expresión para una restricción de tipo Condición.")

    def _sql_definition(self):
        self.ensure_one()
        if self.constraint_type == 'unique':
            columns = ', '.join('"%s"' % f.name for f in self.field_ids)
            return 'UNIQUE (%s)' % columns
        return 'CHECK (%s)' % self.check_expression

    def action_apply(self):
        for rec in self:
            if rec.state == 'applied':
                continue
            table = rec.model_id.model.replace('.', '_')
            query = 'ALTER TABLE "%s" ADD CONSTRAINT "%s" %s' % (
                table, rec.sql_name, rec._sql_definition())
            try:
                rec.env.cr.execute(query)
            except Exception as exc:  # noqa: BLE001
                raise UserError(
                    "No se pudo aplicar la restricción (¿algún registro existente ya la "
                    "incumple?): %s" % exc) from exc
            rec.state = 'applied'
            rec.env['studio.change'].log(
                'constraint', 'studio.model.constraint', rec.id, action='update',
                app_id=rec.model_id.studio_app_id.id,
                summary="Restricción '%s' aplicada en %s" % (rec.name, rec.model_name))

    def action_remove(self):
        for rec in self:
            if rec.state != 'applied':
                continue
            table = rec.model_id.model.replace('.', '_')
            rec.env.cr.execute('ALTER TABLE "%s" DROP CONSTRAINT IF EXISTS "%s"' % (table, rec.sql_name))
            rec.state = 'draft'

    def unlink(self):
        self.action_remove()
        return super().unlink()
