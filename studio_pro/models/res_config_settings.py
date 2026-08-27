# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    studio_ai_provider = fields.Selection(
        [('none', 'Deshabilitado'), ('anthropic', 'Anthropic (Claude)'), ('openai', 'OpenAI')],
        string="Proveedor de IA de Studio Pro", default='none',
        config_parameter='studio_pro.ai_provider')
    studio_ai_api_key = fields.Char(
        string="Clave API de IA de Studio Pro", config_parameter='studio_pro.ai_api_key')
    studio_ai_model = fields.Char(
        string="Modelo de IA de Studio Pro", config_parameter='studio_pro.ai_model',
        default='claude-sonnet-5',
        help="Ej: claude-sonnet-5 / claude-opus-5 para Anthropic, o gpt-4o-mini para OpenAI.")
