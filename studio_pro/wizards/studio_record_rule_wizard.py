# -*- coding: utf-8 -*-
"""Friendly creation of a real ``ir.rule`` (Record Rule / row-level
security). Presets fill in the domain for the two most common cases;
'Personalizado' lets you type any domain, exactly like the native
technical screen — this wizard exists to make the common case one click
and to log it in Studio Pro's change history, not to hide the real thing.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

PRESET_SELECTION = [
    ('own_records', "Solo mis propios registros"),
    ('own_company', "Solo de mi(s) compañía(s)"),
    ('custom', "Dominio personalizado"),
]


class StudioRecordRuleWizard(models.TransientModel):
    _name = 'studio.record.rule.wizard'
    _description = 'Studio Pro — Nueva Regla de Registro (Record Rule)'

    name = fields.Char(required=True)
    model_id = fields.Many2one('ir.model', required=True, string="Modelo")
    group_ids = fields.Many2many(
        'res.groups', string="Grupos",
        help="Vacío = aplica a TODOS los usuarios (incluido el Administrador). Ten cuidado.")
    preset = fields.Selection(PRESET_SELECTION, default='own_records', required=True)
    owner_field_id = fields.Many2one(
        'ir.model.fields', string="Campo de propietario",
        domain="[('model_id', '=', model_id), ('ttype', '=', 'many2one'), ('relation', '=', 'res.users')]",
        help="El campo Many2one a res.users que identifica al 'dueño' del registro (ej: user_id).")
    domain_force = fields.Char(string="Dominio", required=True, default="[('user_id', '=', user.id)]")
    perm_read = fields.Boolean(default=True)
    perm_write = fields.Boolean(default=True)
    perm_create = fields.Boolean(default=True)
    perm_unlink = fields.Boolean(default=True)

    @api.onchange('preset', 'owner_field_id')
    def _onchange_preset(self):
        for wiz in self:
            if wiz.preset == 'own_records':
                field_name = wiz.owner_field_id.name or 'user_id'
                wiz.domain_force = "[('%s', '=', user.id)]" % field_name
            elif wiz.preset == 'own_company':
                wiz.domain_force = "[('company_id', 'in', company_ids)]"

    def action_create(self):
        self.ensure_one()
        try:
            domain = safe_eval(self.domain_force, {'user': self.env.user, 'company_ids': [1]})
        except Exception as exc:  # noqa: BLE001
            raise UserError(self.env._("El dominio no es una expresión de Odoo válida: %s") % exc) from exc
        if not isinstance(domain, (list, tuple)):
            raise UserError(self.env._("El dominio debe ser una lista, ej: [('user_id', '=', user.id)]"))

        rule = self.env['ir.rule'].sudo().create({
            'name': self.name,
            'model_id': self.model_id.id,
            'groups': [(6, 0, self.group_ids.ids)],
            'domain_force': self.domain_force,
            'perm_read': self.perm_read,
            'perm_write': self.perm_write,
            'perm_create': self.perm_create,
            'perm_unlink': self.perm_unlink,
        })
        self.env['studio.change'].log(
            'security', 'ir.rule', rule.id, action='create',
            summary="Regla de registro '%s' creada en %s (%s)" % (
                self.name, self.model_id.model, self.domain_force))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.rule',
            'res_id': rule.id,
            'view_mode': 'form',
            'target': 'current',
        }
