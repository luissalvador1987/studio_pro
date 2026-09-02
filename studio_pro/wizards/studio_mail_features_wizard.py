# -*- coding: utf-8 -*-
"""Habilita (o retira) Chatter y Actividades sobre un modelo YA existente —
la contraparte, para modelos que ya estaban creados, del checkbox que
studio.new.model.wizard ofrece al crear uno nuevo. Usa el mismo mecanismo
100% nativo de Odoo (ir.model.is_mail_thread / is_mail_activity, del propio
módulo mail) — nunca escribe una clase Python."""
from odoo import api, fields, models
from odoo.exceptions import UserError


class StudioMailFeaturesWizard(models.TransientModel):
    _name = 'studio.mail.features.wizard'
    _description = 'Studio Pro — Chatter y Actividades'

    res_model_id = fields.Many2one(
        'ir.model', string="Modelo", required=True, domain=[('state', '=', 'manual')],
        help="Solo modelos creados con Studio Pro — activar esto sobre un modelo estándar de "
             "Odoo (ej. res.partner) no tiene sentido: ya viene con lo que su app trae.")
    has_chatter = fields.Boolean(string="Chatter (mensajes y seguidores)")
    has_activities = fields.Boolean(string="Actividades (requiere Chatter)")

    @api.onchange('res_model_id')
    def _onchange_res_model_id(self):
        if self.res_model_id:
            self.has_chatter = self.res_model_id.is_mail_thread
            self.has_activities = self.res_model_id.is_mail_activity

    @api.onchange('has_chatter')
    def _onchange_has_chatter(self):
        if not self.has_chatter:
            self.has_activities = False

    def action_apply(self):
        self.ensure_one()
        model = self.res_model_id
        was_chatter = model.is_mail_thread
        model.sudo().write({
            'is_mail_thread': self.has_chatter,
            'is_mail_activity': self.has_chatter and self.has_activities,
        })
        if self.has_chatter and not was_chatter:
            forms = self.env['ir.ui.view'].sudo().search([
                ('model', '=', model.model), ('type', '=', 'form'),
            ])
            for view in forms:
                try:
                    view.studio_add_chatter()
                except Exception:
                    pass  # una vista rota no debe frenar el resto; el admin puede agregarlo a mano
        self.env['studio.change'].log(
            'model', 'ir.model', model.id, action='update', app_id=model.studio_app_id.id,
            summary="Chatter=%s / Actividades=%s en %s" % (
                self.has_chatter, self.has_chatter and self.has_activities, model.model))
        return {'type': 'ir.actions.act_window_close'}
