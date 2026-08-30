# -*- coding: utf-8 -*-
"""Guided creation of a real inheriting ``ir.ui.view`` (``inherit_id`` +
``xpath``) — the "clean, update-proof" way to alter an existing view
(native or from any addon), instead of editing its ``arch`` in place. Also
works for QWeb report templates (``ir.ui.view`` with ``type='qweb'``), so
this same wizard covers both "extend a form/list/kanban view" and "extend a
PDF report template" from the request.
"""
from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError

from ..models.studio_app import slugify_technical

POSITION_SELECTION = [
    ('after', "Después (after)"),
    ('before', "Antes (before)"),
    ('inside', "Dentro, al final (inside)"),
    ('replace', "Reemplazar (replace)"),
    ('attributes', "Solo cambiar atributos (attributes)"),
]


class StudioViewInheritWizard(models.TransientModel):
    _name = 'studio.view.inherit.wizard'
    _description = 'Studio Pro — Heredar una Vista o Reporte (xpath)'

    base_view_id = fields.Many2one(
        'ir.ui.view', string="Vista o reporte base", required=True,
        help="La vista que quieres extender — puede ser nativa de Odoo, de cualquier addon "
             "instalado, o creada con Studio Pro.")
    model_name = fields.Char(related='base_view_id.model', readonly=True)
    view_type = fields.Selection(related='base_view_id.type', readonly=True)

    anchor_field_id = fields.Many2one(
        'ir.model.fields', string="Campo de referencia (opcional)",
        domain="[('model_id.model', '=', model_name)]",
        help="Si lo eliges, arma solo la ruta xpath por ti: //field[@name='...']. Para otros "
             "elementos (grupos, botones, pestañas) escribe la ruta xpath a mano abajo.")
    xpath_expr = fields.Char(
        string="Ruta xpath", help="Ej: //field[@name='partner_id'] , //group[@name='sale_info'] , //notebook")
    position = fields.Selection(POSITION_SELECTION, required=True, default='after')
    content = fields.Text(
        string="XML a insertar", default='<field name="x_studio_nuevo_campo"/>',
        help="Para 'attributes' usa, por ejemplo: <attribute name=\"invisible\">1</attribute>")
    name = fields.Char(string="Nombre de la nueva vista")

    @api.onchange('anchor_field_id')
    def _onchange_anchor_field_id(self):
        for wiz in self:
            if wiz.anchor_field_id:
                wiz.xpath_expr = "//field[@name='%s']" % wiz.anchor_field_id.name

    @api.onchange('base_view_id')
    def _onchange_base_view_id(self):
        for wiz in self:
            if wiz.base_view_id and not wiz.name:
                wiz.name = "%s (extendida por Studio Pro)" % wiz.base_view_id.name

    def action_create(self):
        self.ensure_one()
        if not (self.xpath_expr or '').strip():
            raise UserError(self.env._("Indica la ruta xpath (o elige un campo de referencia arriba)."))
        try:
            etree.fromstring('<xpath expr="%s" position="%s">%s</xpath>' % (
                self.xpath_expr, self.position, self.content or ''))
        except etree.XMLSyntaxError as exc:
            raise UserError(self.env._("El XML a insertar no es válido: %s") % exc) from exc

        arch = '<xpath expr="%s" position="%s">%s</xpath>' % (self.xpath_expr, self.position, self.content or '')
        view = self.env['ir.ui.view'].sudo().create({
            'name': self.name or slugify_technical(self.base_view_id.name, prefix='studio_inherit_'),
            'model': self.base_view_id.model,
            'type': self.base_view_id.type,
            'inherit_id': self.base_view_id.id,
            'arch': arch,
        })
        self.env['studio.change'].log(
            'view', 'ir.ui.view', view.id, action='create',
            summary="Vista heredada '%s' creada sobre '%s' (xpath %s %s)" % (
                view.name, self.base_view_id.name, self.xpath_expr, self.position))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'ir.ui.view',
            'res_id': view.id,
            'view_mode': 'form',
            'target': 'current',
        }
