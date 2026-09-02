# -*- coding: utf-8 -*-
"""Standalone "Functions" (Server Actions): unlike an Automation Flow (which
only ever runs when its trigger fires), a Studio Pro Function is meant to be
run on demand — exposed as a contextual action in a model's Action (⚙) menu,
and/or on a schedule. It reuses the exact same step vocabulary as an
automation step (update a field / create a record / send an email / call a
webhook) so the two features stay consistent, but is deliberately kept as
its own model rather than refactored to share code with
`studio.automation.step` at this point — the automation flow compiler is
already tested end-to-end, and duplicating this (fairly small) piece of
logic is safer than risking it.
"""
from odoo import api, fields, models
from odoo.exceptions import UserError


class StudioServerAction(models.Model):
    _name = 'studio.server.action'
    _description = 'Función de Studio Pro (Acción de Servidor)'
    _order = 'name'

    name = fields.Char(string="Nombre", required=True)
    app_id = fields.Many2one('studio.app', string="App", ondelete='cascade')
    model_id = fields.Many2one('ir.model', string="Modelo", required=True, ondelete='cascade',
                                domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model', store=True, readonly=True)

    step_type = fields.Selection([
        ('update', "Actualizar un campo del registro"),
        ('create', "Crear un registro relacionado"),
        ('email', "Enviar un correo"),
        ('activity', "Crear una actividad (recordatorio)"),
        ('followers', "Agregar seguidores"),
        ('webhook', "Llamar a un webhook saliente"),
        ('code', "Código Python (avanzado)"),
    ], string="Qué hace", required=True, default='update')

    field_id = fields.Many2one('ir.model.fields', string="Campo a actualizar",
                                domain="[('model_id', '=', model_id), ('store', '=', True), "
                                        "('ttype', 'not in', ('one2many', 'many2many'))]")
    value_type = fields.Selection([('static', "Valor estático"), ('expression', "Python Expression")],
                                   string="Tipo de valor", default='static')
    value = fields.Char(string="Valor",
                         help="Para un campo booleano usa 'true'/'false'. Para un many2one, el ID numérico "
                              "del registro destino.")

    create_model_id = fields.Many2one('ir.model', string="Modelo a crear")
    create_name = fields.Char(string="Nombre / Título del nuevo registro")
    link_field_id = fields.Many2one('ir.model.fields', string="Vincular usando el campo",
                                     domain="[('model_id', '=', model_id)]")

    template_id = fields.Many2one('mail.template', string="Plantilla de correo",
                                   domain="[('model_id', '=', model_id)]")

    activity_type_id = fields.Many2one(
        'mail.activity.type', string="Tipo de actividad",
        domain="['|', ('res_model', '=', False), ('res_model', '=', model_name)]")
    activity_summary = fields.Char(string="Título de la actividad")
    activity_note = fields.Text(string="Nota")
    activity_date_deadline_range = fields.Integer(string="Vence en", default=0)
    activity_date_deadline_range_type = fields.Selection(
        [('days', "Días"), ('weeks', "Semanas"), ('months', "Meses")],
        string="Unidad de vencimiento", default='days')
    activity_user_id = fields.Many2one('res.users', string="Responsable")

    follower_partner_ids = fields.Many2many('res.partner', string="Agregar como seguidores")

    webhook_url = fields.Char(string="URL del webhook")
    webhook_field_ids = fields.Many2many('ir.model.fields', string="Campos a enviar",
                                          domain="[('model_id', '=', model_id)]")

    code = fields.Text(string="Código Python",
                        help="Variables disponibles: env, record, records, model, log(mensaje). Solo para "
                             "usuarios avanzados — este código se ejecuta con privilegios de Administrador.")

    expose_as_action = fields.Boolean(
        string="Mostrarla en el menú de Acciones (⚙)", default=True,
        help="Aparecerá como una acción disponible sobre este modelo, en listas y formularios.")
    expose_as_cron = fields.Boolean(string="Ejecutar automáticamente por horario")
    cron_interval_number = fields.Integer(string="Cada", default=1)
    cron_interval_type = fields.Selection(
        [('minutes', 'Minutos'), ('hours', 'Horas'), ('days', 'Días'), ('weeks', 'Semanas')],
        string="Unidad", default='days')

    action_server_id = fields.Many2one('ir.actions.server', string="Acción generada", readonly=True, copy=False)
    cron_id = fields.Many2one('ir.cron', string="Tarea programada generada", readonly=True, copy=False)
    state = fields.Selection([('draft', 'Borrador'), ('active', 'Activa')],
                              string="Estado", default='draft', readonly=True, copy=False)

    def action_activate(self):
        for record in self:
            record._compile()
            record.state = 'active'
            self.env['studio.change'].log(
                'automation', 'studio.server.action', record.id, action='update',
                app_id=record.app_id.id, summary="Función '%s' activada" % record.name)
        return True

    def action_deactivate(self):
        for record in self:
            if record.action_server_id:
                record.action_server_id.write({'binding_model_id': False})
            if record.cron_id:
                record.cron_id.active = False
            record.state = 'draft'
        return True

    def action_run_now(self):
        """Manual "Run" button, for functions that aren't exposed as a
        contextual action — mainly useful while testing one before deciding
        how to expose it."""
        for record in self:
            if not record.action_server_id:
                record._compile()
            record.action_server_id.with_context(
                active_model=record.model_id.model, active_ids=[], active_id=False).run()
        return True

    def _compile(self):
        self.ensure_one()
        Server = self.env['ir.actions.server'].sudo()
        vals = self._build_action_vals()
        if self.action_server_id:
            self.action_server_id.write(vals)
            action = self.action_server_id
        else:
            action = Server.create(vals)
            self.action_server_id = action.id

        if self.expose_as_action:
            action.write({
                'binding_model_id': self.model_id.id, 'binding_type': 'action',
                'binding_view_types': 'list,form',
            })
        else:
            action.write({'binding_model_id': False})

        if self.expose_as_cron:
            cron_vals = {
                'name': "[Studio Pro] %s" % self.name,
                'model_id': self.model_id.id,
                'state': 'code',
                'code': "env['ir.actions.server'].browse(%d).with_context("
                        "active_model=model._name, active_ids=[], active_id=False).run()" % action.id,
                'interval_number': self.cron_interval_number or 1,
                'interval_type': self.cron_interval_type,
                'active': True,
            }
            if self.cron_id:
                self.cron_id.write(cron_vals)
            else:
                self.cron_id = self.env['ir.cron'].sudo().create(cron_vals).id
        elif self.cron_id:
            self.cron_id.active = False

        return True

    def _build_action_vals(self):
        self.ensure_one()
        base_vals = {'name': "[Studio Pro] %s" % self.name, 'model_id': self.model_id.id}

        if self.step_type == 'update':
            if not self.field_id:
                raise UserError(self.env._("Elige un campo para actualizar."))
            vals = dict(base_vals, state='object_write', update_path=self.field_id.name,
                        evaluation_type='equation' if self.value_type == 'expression' else 'value')
            ttype = self.field_id.ttype
            if ttype == 'boolean':
                vals['update_boolean_value'] = 'true' if (self.value or '').strip().lower() in ('1', 'true', 'yes') else 'false'
            elif ttype == 'selection' and self.value_type == 'static':
                selection = self.env['ir.model.fields.selection'].search(
                    [('field_id', '=', self.field_id.id), ('value', '=', self.value)], limit=1)
                if not selection:
                    raise UserError(self.env._("'%s' no es una opción válida para el campo %s.") % (
                        self.value, self.field_id.name))
                vals['selection_value'] = selection.id
            elif ttype == 'many2one' and self.value_type == 'static':
                if not (self.value or '').strip().isdigit():
                    raise UserError(self.env._("Para un campo many2one, indica el ID numérico del registro destino."))
                vals['resource_ref'] = '%s,%s' % (self.field_id.relation, int(self.value))
            else:
                vals['value'] = self.value or ''
            return vals

        if self.step_type == 'create':
            if not self.create_model_id:
                raise UserError(self.env._("Elige un modelo donde crear el registro."))
            return dict(base_vals, state='object_create', crud_model_id=self.create_model_id.id,
                        value=self.create_name or '',
                        link_field_id=self.link_field_id.id if self.link_field_id else False)

        if self.step_type == 'email':
            if not self.template_id:
                raise UserError(self.env._("Elige una plantilla de correo."))
            return dict(base_vals, state='mail_post', template_id=self.template_id.id, mail_post_method='email')

        if self.step_type == 'activity':
            if not self.model_id.is_mail_activity:
                raise UserError(self.env._(
                    "Este modelo todavía no tiene 'Actividades' habilitadas — activalas primero "
                    "(asistente 'Chatter y Actividades') antes de crear una Función de Actividad."))
            if not self.activity_type_id:
                raise UserError(self.env._("Elige un tipo de actividad."))
            return dict(base_vals, state='next_activity', activity_type_id=self.activity_type_id.id,
                        activity_summary=self.activity_summary or '', activity_note=self.activity_note or '',
                        activity_date_deadline_range=max(self.activity_date_deadline_range, 0),
                        activity_date_deadline_range_type=self.activity_date_deadline_range_type,
                        activity_user_type='specific', activity_user_id=self.activity_user_id.id or False)

        if self.step_type == 'followers':
            if not self.model_id.is_mail_thread:
                raise UserError(self.env._(
                    "Este modelo todavía no tiene el Chatter habilitado — activalo primero (asistente "
                    "'Chatter y Actividades') antes de crear una Función de Seguidores."))
            if not self.follower_partner_ids:
                raise UserError(self.env._("Elige al menos un contacto para agregar como seguidor."))
            return dict(base_vals, state='followers', partner_ids=[(6, 0, self.follower_partner_ids.ids)])

        if self.step_type == 'webhook':
            if not self.webhook_url:
                raise UserError(self.env._("Indica una URL de webhook."))
            return dict(base_vals, state='webhook', webhook_url=self.webhook_url,
                        webhook_field_ids=[(6, 0, self.webhook_field_ids.ids)])

        if self.step_type == 'code':
            if not self.code:
                raise UserError(self.env._("Escribe el código Python a ejecutar."))
            return dict(base_vals, state='code', code=self.code)

        raise UserError(self.env._("Tipo de función no soportado: %s") % self.step_type)
