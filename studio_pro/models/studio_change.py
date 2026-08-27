# -*- coding: utf-8 -*-
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StudioChange(models.Model):
    """Audit / version log for everything created or modified through Studio
    Pro. This is what lets Studio Pro offer a change history, a best-effort
    revert, and a real module export — none of which stock Odoo Studio
    provides in an inspectable way.
    """
    _name = 'studio.change'
    _description = 'Historial de Cambios de Studio Pro'
    _order = 'id desc'
    _rec_name = 'summary'

    app_id = fields.Many2one('studio.app', string="App", ondelete='cascade', index=True)
    summary = fields.Char(string="Resumen", required=True)
    studio_type = fields.Selection([
        ('app', 'App'),
        ('model', 'Modelo'),
        ('field', 'Campo'),
        ('view', 'Vista'),
        ('automation', 'Automatización'),
        ('report', 'Reporte'),
        ('access', 'Permiso de Acceso'),
        ('ai', 'Asistente de IA'),
    ], string="Tipo", required=True, index=True)
    action = fields.Selection([
        ('create', 'Creación'),
        ('update', 'Actualización'),
        ('delete', 'Eliminación'),
    ], string="Acción", required=True, default='create')
    res_model = fields.Char(string="Modelo técnico", required=True)
    res_id = fields.Integer(string="ID del registro", required=True)
    vals_before = fields.Text(string="Valores anteriores",
                               help="Copia en JSON de los campos afectados antes del cambio (usada para revertir).")
    vals_after = fields.Text(string="Valores nuevos", help="Copia en JSON de los campos afectados después del cambio.")
    xml_id = fields.Char(string="ID externo", help="ID externo usado para exportar este registro como parte de un módulo.")
    reverted = fields.Boolean(string="Revertido", default=False, copy=False)
    user_id = fields.Many2one('res.users', string="Usuario", default=lambda self: self.env.user, readonly=True)

    @api.model
    def log(self, studio_type, res_model, res_id, action='create', summary=None,
            vals_before=None, vals_after=None, app_id=None, xml_id=None):
        """Record one change. Safe to call even if serialization of a value
        fails (falls back to str()) so logging never blocks the real action.
        """
        def dump(vals):
            if vals is None:
                return False
            try:
                return json.dumps(vals, default=str, ensure_ascii=False)
            except Exception:  # noqa: BLE001
                return str(vals)

        try:
            return self.sudo().create({
                'app_id': app_id,
                'summary': summary or ('%s %s#%s' % (action, res_model, res_id)),
                'studio_type': studio_type,
                'action': action,
                'res_model': res_model,
                'res_id': res_id,
                'vals_before': dump(vals_before),
                'vals_after': dump(vals_after),
                'xml_id': xml_id,
            })
        except Exception:  # noqa: BLE001
            _logger.exception("Studio Pro: could not write change log entry")
            return self.browse()

    def action_revert(self):
        """Best-effort revert: only re-applies simple stored field values that
        were captured in ``vals_before``. Structural changes (a whole model or
        field being *created*) cannot be safely auto-reverted from here since
        other customizations may depend on them by then; use the model/field
        list to delete those instead.
        """
        for change in self:
            if change.reverted:
                continue
            if change.action != 'update' or not change.vals_before:
                raise UserError(_(
                    "Solo se pueden revertir automáticamente cambios simples de campos. "
                    "Elimina el registro desde su propia vista de lista en su lugar."
                ))
            vals = json.loads(change.vals_before)
            record = self.env[change.res_model].sudo().browse(change.res_id)
            if record.exists():
                record.write(vals)
            change.reverted = True
        return True
