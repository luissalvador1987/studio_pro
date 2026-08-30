# -*- coding: utf-8 -*-
"""Injects custom JavaScript/CSS into Odoo's backend or website frontend
without writing a single file to disk.

Mechanism: the code is stored as a normal ``ir.attachment`` (served at
``/web/content/<id>``), and an ``ir.asset`` record — Odoo's own, native,
data-driven way of adding a file to an assets bundle since v15 — points at
that URL with an ``append`` directive. Odoo's asset-bundle resolver
explicitly recognizes a non-addon-relative path like ``/web/content/123``
as "an attachment url" and loads it with a plain ``<script src="...">`` /
``<link rel="stylesheet">`` tag, exactly like a real static file would be.
"""
from odoo import api, fields, models

BUNDLE_SELECTION = [
    ('web.assets_backend', "Panel de control (backend, usuarios con sesión)"),
    ('web.assets_frontend', "Sitio web público (frontend)"),
]


class StudioCustomCode(models.Model):
    _name = 'studio.custom.code'
    _description = 'Studio Pro — Código JS/CSS personalizado'
    _order = 'name'

    name = fields.Char(required=True)
    code_type = fields.Selection([('js', "JavaScript"), ('css', "CSS")], required=True, default='js')
    target_bundle = fields.Selection(BUNDLE_SELECTION, required=True, default='web.assets_backend')
    code = fields.Text(required=True)
    active = fields.Boolean(default=True)
    attachment_id = fields.Many2one('ir.attachment', readonly=True, copy=False)
    asset_id = fields.Many2one('ir.asset', readonly=True, copy=False)
    attachment_url = fields.Char(related='attachment_id.url', string="URL servida")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_asset()
        return records

    def write(self, vals):
        res = super().write(vals)
        if set(vals) & {'code', 'code_type', 'target_bundle', 'active', 'name'}:
            self._sync_asset()
        return res

    def unlink(self):
        self.mapped('asset_id').sudo().unlink()
        self.mapped('attachment_id').sudo().unlink()
        return super().unlink()

    def _mimetype(self):
        return 'application/javascript' if self.code_type == 'js' else 'text/css'

    def _sync_asset(self):
        Attachment = self.env['ir.attachment'].sudo()
        Asset = self.env['ir.asset'].sudo()
        for rec in self:
            ext = 'js' if rec.code_type == 'js' else 'css'
            if rec.attachment_id:
                rec.attachment_id.write({
                    'raw': rec.code.encode('utf-8'), 'mimetype': rec._mimetype(),
                })
            else:
                rec.attachment_id = Attachment.create({
                    'name': 'studio_custom_code_%d.%s' % (rec.id, ext),
                    'raw': rec.code.encode('utf-8'),
                    'mimetype': rec._mimetype(),
                    'public': True,
                })
            url = '/web/content/%d?unique=%s' % (rec.attachment_id.id, rec.attachment_id.checksum or '0')
            if rec.asset_id:
                rec.asset_id.write({
                    'path': url, 'bundle': rec.target_bundle, 'active': rec.active,
                })
            else:
                rec.asset_id = Asset.create({
                    'name': 'Studio Pro: %s' % rec.name,
                    'bundle': rec.target_bundle,
                    'directive': 'append',
                    'path': url,
                    'active': rec.active,
                })
            self.env['studio.change'].log(
                'custom_code', 'studio.custom.code', rec.id, action='update',
                summary="Código %s personalizado '%s' actualizado (%s)" % (
                    rec.code_type.upper(), rec.name, rec.target_bundle))
