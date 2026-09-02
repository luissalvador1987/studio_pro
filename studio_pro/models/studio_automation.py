# -*- coding: utf-8 -*-
"""Multi-step automation flows.

Odoo's own ``base.automation`` already runs a *sequence* of server actions
per trigger (``action_server_ids``), which we reuse directly whenever a flow
has no branching. As soon as one step is a "Condition" step, real
if-this-then-stop-else-continue branching is required, which native
``base.automation`` cannot express with a plain list of actions — so in that
case we compile the whole flow into a single generated "Execute Python Code"
action that calls the previously-built per-step actions in order, guarded by
the evaluated conditions. The generated code only ever interpolates trusted,
structured data (integers and ``ast.literal_eval``-validated domains), never
free text, and only Studio Pro Builders (System Administrators) can reach
this feature — the same trust boundary Odoo Studio itself relies on for its
own "Execute Python Code" automation action.
"""
import ast
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

TRIGGER_SELECTION = [
    ('on_create', "Al crear"),
    ('on_write', "Al actualizar"),
    ('on_create_or_write', "Al guardar (creación o actualización)"),
    ('on_unlink', "Al eliminar"),
    ('on_time', "Según un campo de fecha"),
    ('on_webhook', "Al recibir un webhook"),
]


class StudioAutomationFlow(models.Model):
    _name = 'studio.automation.flow'
    _description = 'Flujo de Automatización de Studio Pro'
    _order = 'sequence, id'

    name = fields.Char(string="Nombre", required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    app_id = fields.Many2one('studio.app', string="App", ondelete='cascade')
    model_id = fields.Many2one('ir.model', string="Modelo", required=True, ondelete='cascade',
                                domain=[('transient', '=', False)])
    model_name = fields.Char(related='model_id.model', store=True, readonly=True)

    trigger = fields.Selection(TRIGGER_SELECTION, string="Disparador", default='on_create_or_write', required=True)
    filter_domain = fields.Char(string="Aplicar sobre", default='[]',
                                 help="Ejecuta el flujo solo sobre registros que coincidan con este dominio.")
    trg_date_id = fields.Many2one('ir.model.fields', string="Campo de fecha disparador",
                                   domain="[('model_id', '=', model_id), ('ttype', 'in', ('date', 'datetime'))]")
    trg_date_range = fields.Integer(string="Demora tras la fecha disparadora")
    trg_date_range_type = fields.Selection(
        [('minutes', 'Minutos'), ('hour', 'Horas'), ('day', 'Días'), ('month', 'Meses')],
        string="Tipo de demora", default='hour')

    step_ids = fields.One2many('studio.automation.step', 'flow_id', string="Pasos", copy=True)
    has_condition_step = fields.Boolean(compute='_compute_has_condition_step')

    automation_id = fields.Many2one('base.automation', string="Automatización", readonly=True, copy=False)
    generated_action_ids = fields.Many2many('ir.actions.server', string="Acciones generadas",
                                             readonly=True, copy=False,
                                             help="Técnico: las acciones de servidor que este flujo posee "
                                                  "actualmente, para que al recompilar se limpie exactamente "
                                                  "lo que se generó la vez anterior.")
    webhook_url = fields.Char(string="URL del webhook", related='automation_id.url', readonly=True)
    state = fields.Selection([('draft', 'Borrador'), ('active', 'Activo'), ('disabled', 'Deshabilitado')],
                              string="Estado", default='draft', readonly=True, copy=False)
    last_error = fields.Text(string="Último error", readonly=True, copy=False)

    @api.depends('step_ids.step_type')
    def _compute_has_condition_step(self):
        for flow in self:
            flow.has_condition_step = any(s.step_type == 'condition' for s in flow.step_ids)

    # ------------------------------------------------------------------
    # Compilation
    # ------------------------------------------------------------------
    def action_activate(self):
        for flow in self:
            if not flow.step_ids:
                raise UserError(self.env._("Agrega al menos un paso antes de activar el flujo."))
            flow._compile()
            flow.state = 'active'
            self.env['studio.change'].log(
                'automation', 'studio.automation.flow', flow.id, action='update',
                app_id=flow.app_id.id, summary="Automatización '%s' activada" % flow.name)
        return True

    def action_disable(self):
        for flow in self:
            flow.state = 'disabled'
            if flow.automation_id:
                flow.automation_id.active = False
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft'})
        return True

    def _compile(self):
        self.ensure_one()
        Server = self.env['ir.actions.server'].sudo()
        Automation = self.env['base.automation'].sudo()

        steps = self.step_ids.sorted('sequence')
        previously_generated = self.generated_action_ids

        action_by_step = {}
        for step in steps.filtered(lambda s: s.step_type != 'condition'):
            action_by_step[step.id] = step._build_action(Server)
        new_generated = Server.browse().union(*action_by_step.values()) if action_by_step else Server.browse()

        if self.has_condition_step:
            code = self._build_flow_code(steps, action_by_step)
            root = Server.create({
                'name': "[Studio Pro] %s (flow)" % self.name,
                'model_id': self.model_id.id,
                'state': 'code',
                'code': code,
            })
            new_generated |= root
            action_server_ids = [(6, 0, [root.id])]
        else:
            ordered = [action_by_step[s.id].id for s in steps if s.id in action_by_step]
            action_server_ids = [(6, 0, ordered)]

        vals = {
            'name': self.name,
            'model_id': self.model_id.id,
            'trigger': self.trigger,
            'active': True,
        }
        if self.automation_id:
            self.automation_id.write(vals)
            automation = self.automation_id
        else:
            automation = Automation.create(vals)
            self.automation_id = automation.id

        # second write: apply condition/date fields *after* the trigger has
        # already been set once, mirroring how the standard UI behaves and
        # avoiding surprises from the trigger-dependent computed defaults.
        follow_up = {'filter_domain': self.filter_domain or '[]', 'action_server_ids': action_server_ids}
        if self.trigger == 'on_time':
            follow_up.update({
                'trg_date_id': self.trg_date_id.id if self.trg_date_id else False,
                'trg_date_range': self.trg_date_range,
                'trg_date_range_type': self.trg_date_range_type,
            })
        automation.write(follow_up)

        self.generated_action_ids = [(6, 0, new_generated.ids)]
        stale = previously_generated - new_generated
        stale.unlink()
        return True

    def _build_flow_code(self, steps, action_by_step):
        """Generate the body of a single "Execute Python Code" action that
        replays every step in order, skipping everything after a condition
        that evaluates to False. Only integers and literal domains coming
        from our own structured fields are interpolated — never raw text.
        """
        lines = ["_continue = True"]
        ctx = ("with_context(active_id=record.id, active_ids=record.ids, "
               "active_model=record._name)")
        for step in steps:
            if step.step_type == 'condition':
                domain = step._get_safe_domain()
                lines.append("if _continue:")
                lines.append("    _continue = bool(record) and record.filtered_domain(%r)" % (domain,))
            else:
                action = action_by_step.get(step.id)
                if not action:
                    continue
                lines.append("if _continue:")
                lines.append("    env['ir.actions.server'].browse(%d).%s.run()" % (action.id, ctx))
        return "\n".join(lines)


class StudioAutomationStep(models.Model):
    _name = 'studio.automation.step'
    _description = 'Paso de Automatización de Studio Pro'
    _order = 'sequence, id'

    flow_id = fields.Many2one('studio.automation.flow', string="Flujo", required=True, ondelete='cascade')
    model_id = fields.Many2one('ir.model', related='flow_id.model_id', store=False)
    model_name = fields.Char(related='model_id.model', store=False)
    sequence = fields.Integer(default=10)
    step_type = fields.Selection([
        ('condition', "Condición (detiene el flujo si no se cumple)"),
        ('update', "Actualizar un campo del registro"),
        ('create', "Crear un registro relacionado"),
        ('email', "Enviar un correo"),
        ('activity', "Crear una actividad (recordatorio)"),
        ('followers', "Agregar seguidores"),
        ('webhook', "Llamar a un webhook saliente"),
    ], string="Tipo de paso", required=True, default='update')

    # condición
    domain = fields.Char(string="Dominio", default='[]',
                          help="El flujo se detiene aquí (para este registro) si no coincide.")

    # actualizar — los campos many2many/one2many no son compatibles con este
    # paso simple (necesitan una operación de agregar/quitar/fijar/vaciar);
    # usa la pantalla estándar de Reglas de Automatización (Ajustes > Técnico)
    # para esos casos.
    field_id = fields.Many2one('ir.model.fields', string="Campo a actualizar",
                                domain="[('model_id', '=', model_id), ('store', '=', True), "
                                        "('ttype', 'not in', ('one2many', 'many2many'))]")
    value_type = fields.Selection([('static', "Valor estático"), ('expression', "Expresión Python")],
                                   string="Tipo de valor", default='static')
    value = fields.Char(string="Valor",
                         help="Para un campo booleano usa 'true'/'false'. Para un many2one, el ID numérico "
                              "del registro destino.")

    # crear
    create_model_id = fields.Many2one('ir.model', string="Modelo a crear")
    create_name = fields.Char(string="Nombre / Título del nuevo registro")
    link_field_id = fields.Many2one('ir.model.fields', string="Vincular usando el campo",
                                     domain="[('model_id', '=', model_id)]",
                                     help="Campo opcional del registro original usado para guardar/agregar el "
                                          "ID del nuevo registro.")

    # correo
    template_id = fields.Many2one('mail.template', string="Plantilla de correo",
                                   domain="[('model_id', '=', model_id)]")

    # actividad — usa el mecanismo nativo de ir.actions.server (state='next_activity',
    # del propio módulo mail), solo en modo "usuario fijo" por simplicidad.
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

    # seguidores — mecanismo nativo (state='followers', del propio módulo mail).
    follower_partner_ids = fields.Many2many('res.partner', string="Agregar como seguidores")

    # webhook
    webhook_url = fields.Char(string="URL del webhook")
    webhook_field_ids = fields.Many2many('ir.model.fields', string="Campos a enviar",
                                          domain="[('model_id', '=', model_id)]")

    def _get_safe_domain(self):
        self.ensure_one()
        raw = self.domain or '[]'
        try:
            value = ast.literal_eval(raw)
        except (ValueError, SyntaxError) as e:
            raise ValidationError(self.env._("Dominio inválido %r en un paso de condición: %s") % (raw, e))
        if not isinstance(value, list):
            raise ValidationError(self.env._("El dominio de la condición debe ser una lista de tuplas, se "
                                              "recibió: %r") % (raw,))
        return value

    def _build_action(self, Server):
        self.ensure_one()
        base_vals = {
            'name': "[Studio Pro] %s / step %s" % (self.flow_id.name, self.sequence),
            'model_id': self.flow_id.model_id.id,
            'sequence': self.sequence,
        }

        if self.step_type == 'update':
            if not self.field_id:
                raise UserError(self.env._("Paso %s: elige un campo para actualizar.") % self.sequence)
            # `update_path` (a plain field name here, no relation traversal) is
            # what actually drives the write; `update_field_id` is only ever
            # *derived* from it by `_compute_crud_relations` and must not be
            # set directly, or the action silently does nothing.
            vals = dict(base_vals, state='object_write', update_path=self.field_id.name,
                        evaluation_type='equation' if self.value_type == 'expression' else 'value')
            ttype = self.field_id.ttype
            if ttype == 'boolean':
                vals['update_boolean_value'] = 'true' if (self.value or '').strip().lower() in ('1', 'true', 'yes') else 'false'
            elif ttype == 'selection' and self.value_type == 'static':
                selection = self.env['ir.model.fields.selection'].search(
                    [('field_id', '=', self.field_id.id), ('value', '=', self.value)], limit=1)
                if not selection:
                    raise UserError(self.env._("'%s' no es una opción válida para el campo %s.") % (self.value, self.field_id.name))
                vals['selection_value'] = selection.id
            elif ttype in ('many2one',) and self.value_type == 'static':
                if not (self.value or '').strip().isdigit():
                    raise UserError(self.env._("Para un campo many2one, indica el ID numérico del registro destino."))
                vals['resource_ref'] = '%s,%s' % (self.field_id.relation, int(self.value))
            else:
                vals['value'] = self.value or ''
            return Server.create(vals)

        if self.step_type == 'create':
            if not self.create_model_id:
                raise UserError(self.env._("Paso %s: elige un modelo donde crear el registro.") % self.sequence)
            vals = dict(base_vals, state='object_create',
                        crud_model_id=self.create_model_id.id,
                        value=self.create_name or '',
                        link_field_id=self.link_field_id.id if self.link_field_id else False)
            return Server.create(vals)

        if self.step_type == 'email':
            if not self.template_id:
                raise UserError(self.env._("Paso %s: elige una plantilla de correo.") % self.sequence)
            vals = dict(base_vals, state='mail_post', template_id=self.template_id.id, mail_post_method='email')
            return Server.create(vals)

        if self.step_type == 'activity':
            if not self.flow_id.model_id.is_mail_activity:
                raise UserError(self.env._(
                    "Paso %s: este modelo todavía no tiene 'Actividades' habilitadas — activalas primero "
                    "(asistente 'Chatter y Actividades') antes de crear un paso de Actividad.") % self.sequence)
            if not self.activity_type_id:
                raise UserError(self.env._("Paso %s: elige un tipo de actividad.") % self.sequence)
            vals = dict(base_vals, state='next_activity', activity_type_id=self.activity_type_id.id,
                        activity_summary=self.activity_summary or '', activity_note=self.activity_note or '',
                        activity_date_deadline_range=max(self.activity_date_deadline_range, 0),
                        activity_date_deadline_range_type=self.activity_date_deadline_range_type,
                        activity_user_type='specific', activity_user_id=self.activity_user_id.id or False)
            return Server.create(vals)

        if self.step_type == 'followers':
            if not self.flow_id.model_id.is_mail_thread:
                raise UserError(self.env._(
                    "Paso %s: este modelo todavía no tiene el Chatter habilitado — activalo primero "
                    "(asistente 'Chatter y Actividades') antes de crear un paso de Seguidores.") % self.sequence)
            if not self.follower_partner_ids:
                raise UserError(self.env._("Paso %s: elige al menos un contacto para agregar como seguidor.") % self.sequence)
            vals = dict(base_vals, state='followers', partner_ids=[(6, 0, self.follower_partner_ids.ids)])
            return Server.create(vals)

        if self.step_type == 'webhook':
            if not self.webhook_url:
                raise UserError(self.env._("Paso %s: indica una URL de webhook.") % self.sequence)
            vals = dict(base_vals, state='webhook', webhook_url=self.webhook_url,
                        webhook_field_ids=[(6, 0, self.webhook_field_ids.ids)])
            return Server.create(vals)

        raise UserError(self.env._(
            "Los pasos de condición se compilan en línea y no generan una acción independiente."))
