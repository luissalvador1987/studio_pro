# -*- coding: utf-8 -*-
"""AI Assistant: turns a plain-language request into a *reviewable* plan
(new fields and/or a draft automation flow) that a human must explicitly
apply — the assistant never writes to the database by itself. It is just
another caller of the same trusted builder methods used by the manual
wizards, so it carries no extra risk beyond a bad LLM suggestion, which the
review step is there to catch.
"""
import ast
import json
import logging
import re

import requests

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.studio_app import slugify_technical
from .studio_new_field_wizard import FIELD_TYPES, RELATIONAL_TYPES

_logger = logging.getLogger(__name__)

ALLOWED_TTYPES = {t for t, _ in FIELD_TYPES}
ALLOWED_TRIGGERS = ('on_create', 'on_write', 'on_create_or_write', 'on_unlink')
ALLOWED_STEP_TYPES = ('condition', 'update', 'email', 'webhook')

SYSTEM_PROMPT = """You are an assistant that plans customizations for an Odoo database.
Answer with ONLY one JSON object (no markdown fences, no commentary) matching exactly this shape:
{
  "fields": [
    {"model": "<technical model name, e.g. res.partner>", "label": "<human label>",
     "ttype": "<one of char/text/html/integer/float/monetary/boolean/date/datetime/selection/many2one/many2many/binary>",
     "required": false, "relation": "<technical model name, only for many2one/many2many>",
     "selection_options": "<only for selection, e.g. 'new:New,done:Done'>"}
  ],
  "automation": null | {
    "name": "<short name>", "model": "<technical model name>",
    "trigger": "<one of on_create/on_write/on_create_or_write/on_unlink>",
    "steps": [
      {"type": "condition", "domain": "<a valid Odoo domain as a Python literal string, e.g. \\"[('state','=','done')]\\">"},
      {"type": "update", "field": "<technical field name on the model>", "value": "<value as text>"}
    ]
  }
}
Only ever propose "one2many"-free, "create"-free plans. Use "fields": [] and/or "automation": null when nothing applies.
Never invent a model or field name you are not reasonably confident exists or was mentioned by the user.
"""


class StudioAiAssistantWizard(models.TransientModel):
    _name = 'studio.ai.assistant.wizard'
    _description = 'Studio Pro — Asistente de IA'

    app_id = fields.Many2one('studio.app', string="App")
    prompt = fields.Text(required=True, string="¿Qué quieres construir?")
    plan_json = fields.Text(readonly=True)
    plan_preview = fields.Text(string="Plan propuesto", readonly=True)
    state = fields.Selection([('draft', 'Borrador'), ('previewed', 'Previsualizado'), ('applied', 'Aplicado')],
                              string="Estado", default='draft', readonly=True)
    error_message = fields.Text(string="Mensaje de error", readonly=True)

    # ------------------------------------------------------------------
    def _get_provider_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        provider = ICP.get_param('studio_pro.ai_provider', 'none')
        api_key = ICP.get_param('studio_pro.ai_api_key')
        model = ICP.get_param('studio_pro.ai_model') or (
            'claude-sonnet-5' if provider == 'anthropic' else 'gpt-4o-mini')
        if provider == 'none' or not api_key:
            raise UserError(self.env._(
                "Primero configura un proveedor de IA y una clave API en Ajustes > Studio Pro."))
        return provider, api_key, model

    def _call_llm(self, provider, api_key, model):
        if provider == 'anthropic':
            resp = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={
                    'model': model,
                    'max_tokens': 2000,
                    'system': SYSTEM_PROMPT,
                    'messages': [{'role': 'user', 'content': self.prompt}],
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()['content'][0]['text']
        elif provider == 'openai':
            resp = requests.post(
                'https://api.openai.com/v1/chat/completions',
                headers={'Authorization': 'Bearer %s' % api_key, 'content-type': 'application/json'},
                json={
                    'model': model,
                    'temperature': 0,
                    'messages': [
                        {'role': 'system', 'content': SYSTEM_PROMPT},
                        {'role': 'user', 'content': self.prompt},
                    ],
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()['choices'][0]['message']['content']
        raise UserError(self.env._("Proveedor de IA desconocido: %s") % provider)

    def _validate_plan(self, raw_text):
        cleaned = re.sub(r'^```(json)?|```$', '', raw_text.strip(), flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
        except ValueError as e:
            raise UserError(self.env._("La respuesta de la IA no era un JSON válido: %s") % e)
        if not isinstance(data, dict):
            raise UserError(self.env._("La respuesta de la IA debe ser un objeto JSON."))

        fields_spec = data.get('fields') or []
        if not isinstance(fields_spec, list):
            raise UserError(self.env._("'fields' debe ser una lista."))
        clean_fields = []
        for spec in fields_spec:
            model_name = spec.get('model')
            if not model_name or not self.env['ir.model'].sudo().search_count([('model', '=', model_name)]):
                raise UserError(self.env._("Modelo desconocido en el plan de la IA: %r") % model_name)
            ttype = spec.get('ttype')
            if ttype not in ALLOWED_TTYPES:
                raise UserError(self.env._("Tipo de campo no soportado en el plan de la IA: %r") % ttype)
            if ttype in RELATIONAL_TYPES and not (spec.get('relation') and
                    self.env['ir.model'].sudo().search_count([('model', '=', spec['relation'])])):
                raise UserError(self.env._("Falta el modelo relacionado (o es desconocido) para el campo %r.") % spec.get('label'))
            clean_fields.append({
                'model': model_name,
                'label': spec.get('label') or 'Nuevo campo',
                'ttype': ttype,
                'required': bool(spec.get('required')),
                'relation': spec.get('relation') or False,
                'selection_options': spec.get('selection_options') or '',
            })

        clean_automation = None
        automation_spec = data.get('automation')
        if automation_spec:
            model_name = automation_spec.get('model')
            if not model_name or not self.env['ir.model'].sudo().search_count([('model', '=', model_name)]):
                raise UserError(self.env._("Modelo desconocido para la automatización propuesta por la IA: %r") % model_name)
            trigger = automation_spec.get('trigger')
            if trigger not in ALLOWED_TRIGGERS:
                raise UserError(self.env._("Disparador no soportado en el plan de la IA: %r") % trigger)
            clean_steps = []
            for step in automation_spec.get('steps') or []:
                step_type = step.get('type')
                if step_type not in ALLOWED_STEP_TYPES:
                    raise UserError(self.env._("Tipo de paso de automatización no soportado en el plan de la IA: %r") % step_type)
                if step_type == 'condition':
                    domain_raw = step.get('domain') or '[]'
                    try:
                        domain = ast.literal_eval(domain_raw)
                    except (ValueError, SyntaxError):
                        raise UserError(self.env._("Dominio inválido en el plan de la IA: %r") % domain_raw)
                    if not isinstance(domain, list):
                        raise UserError(self.env._("El dominio debe ser una lista: %r") % domain_raw)
                    clean_steps.append({'type': 'condition', 'domain': repr(domain)})
                elif step_type == 'update':
                    fname = step.get('field')
                    if not fname or not self.env['ir.model.fields'].sudo().search_count(
                            [('model', '=', model_name), ('name', '=', fname)]):
                        raise UserError(self.env._("Campo desconocido %r para el paso de actualización propuesto por la IA.") % fname)
                    clean_steps.append({'type': 'update', 'field': fname, 'value': str(step.get('value') or '')})
                else:
                    # los pasos de email / webhook requieren elegir una plantilla o
                    # URL a mano por seguridad; se dejan como pendiente manual en
                    # la previsualización.
                    clean_steps.append({'type': step_type, 'todo': True})
            clean_automation = {
                'name': automation_spec.get('name') or 'Automatización de IA',
                'model': model_name,
                'trigger': trigger,
                'steps': clean_steps,
            }

        return {'fields': clean_fields, 'automation': clean_automation}

    def _build_preview(self, plan):
        lines = []
        for f in plan['fields']:
            lines.append("+ Campo '%s' (%s) en %s%s" % (
                f['label'], f['ttype'], f['model'], ' [obligatorio]' if f['required'] else ''))
        if plan['automation']:
            a = plan['automation']
            lines.append("+ Automatización '%s' en %s, disparador=%s" % (a['name'], a['model'], a['trigger']))
            for s in a['steps']:
                if s['type'] == 'condition':
                    lines.append("    - detener a menos que %s" % s['domain'])
                elif s['type'] == 'update':
                    lines.append("    - fijar %s = %s" % (s['field'], s['value']))
                else:
                    lines.append("    - (paso %s: termina de configurarlo manualmente después de aplicar)" % s['type'])
        if not lines:
            lines.append("Nada que crear — intenta reformular tu solicitud.")
        return "\n".join(lines)

    def action_generate_plan(self):
        self.ensure_one()
        provider, api_key, model = self._get_provider_config()
        try:
            raw_text = self._call_llm(provider, api_key, model)
            plan = self._validate_plan(raw_text)
        except UserError as e:
            self.write({'state': 'draft', 'error_message': str(e)})
            raise
        except Exception as e:  # noqa: BLE001
            _logger.exception("Studio Pro AI Assistant call failed")
            self.write({'state': 'draft', 'error_message': str(e)})
            raise UserError(self.env._("La llamada a la IA falló: %s") % e)

        self.write({
            'plan_json': json.dumps(plan),
            'plan_preview': self._build_preview(plan),
            'state': 'previewed',
            'error_message': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply_plan(self):
        self.ensure_one()
        if self.state != 'previewed' or not self.plan_json:
            raise UserError(self.env._("Genera y revisa un plan antes de aplicarlo."))
        plan = json.loads(self.plan_json)

        created_fields = self.env['ir.model.fields']
        for f in plan['fields']:
            model = self.env['ir.model'].sudo().search([('model', '=', f['model'])], limit=1)
            name = slugify_technical(f['label'], prefix='x_studio_')
            if self.env['ir.model.fields'].sudo().search_count([('model_id', '=', model.id), ('name', '=', name)]):
                continue
            vals = {
                'model_id': model.id, 'name': name, 'field_description': f['label'],
                'ttype': f['ttype'], 'required': f['required'], 'state': 'manual',
            }
            if f['relation']:
                vals['relation'] = f['relation']
            if f['ttype'] == 'selection' and f['selection_options']:
                options = []
                for chunk in f['selection_options'].split(','):
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    value, _, label = chunk.partition(':')
                    options.append((value.strip(), (label or value).strip()))
                vals['selection_ids'] = [(0, 0, {'value': v, 'name': l, 'sequence': i})
                                          for i, (v, l) in enumerate(options)]
            field = self.env['ir.model.fields'].sudo().create(vals)
            created_fields |= field
            self.env['studio.change'].log(
                'ai', 'ir.model.fields', field.id, action='create', app_id=self.app_id.id,
                summary="El Asistente de IA agregó el campo '%s' en %s" % (f['label'], f['model']))

        created_flow = self.env['studio.automation.flow'].browse()
        if plan['automation']:
            a = plan['automation']
            model = self.env['ir.model'].sudo().search([('model', '=', a['model'])], limit=1)
            step_cmds = []
            for i, s in enumerate(a['steps']):
                vals = {'sequence': (i + 1) * 10}
                if s['type'] == 'condition':
                    vals.update({'step_type': 'condition', 'domain': s['domain']})
                elif s['type'] == 'update':
                    field = self.env['ir.model.fields'].sudo().search(
                        [('model_id', '=', model.id), ('name', '=', s['field'])], limit=1)
                    vals.update({'step_type': 'update', 'field_id': field.id, 'value': s['value']})
                else:
                    continue  # email/webhook: left for the user to finish manually
                step_cmds.append((0, 0, vals))
            created_flow = self.env['studio.automation.flow'].sudo().create({
                'name': a['name'], 'app_id': self.app_id.id, 'model_id': model.id,
                'trigger': a['trigger'], 'step_ids': step_cmds,
                # left in draft: a human must review and activate it explicitly.
            })
            self.env['studio.change'].log(
                'ai', 'studio.automation.flow', created_flow.id, action='create', app_id=self.app_id.id,
                summary="El Asistente de IA creó el borrador de automatización '%s' (aún inactiva)" % a['name'])

        self.state = 'applied'
        if created_flow:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'studio.automation.flow',
                'res_id': created_flow.id,
                'view_mode': 'form',
            }
        return {'type': 'ir.actions.act_window_close'}
