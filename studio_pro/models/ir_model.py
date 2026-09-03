# -*- coding: utf-8 -*-
"""Thin extensions of core models so Studio Pro can (a) group things created
under an "App" and (b) offer a structural view editor on top of any
ir.ui.view, for any model, exactly like Odoo Studio's own view editor.
"""
import logging

from lxml import etree

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# tags that are considered "editable rows" by the Studio Pro view editor
_EDITABLE_TAGS = ('field', 'button', 'label', 'separator')
# never let the field list editor touch these — they are structural / technical
_SKIP_FIELD_NAMES = {'id', 'display_name', 'create_date', 'create_uid', 'write_date', 'write_uid'}


class IrModel(models.Model):
    _inherit = 'ir.model'

    studio_app_id = fields.Many2one('studio.app', string="App de Studio Pro", ondelete='set null', index=True)


class BaseAutomation(models.Model):
    _inherit = 'base.automation'

    studio_app_id = fields.Many2one('studio.app', string="App de Studio Pro", ondelete='set null', index=True)
    studio_flow_id = fields.One2many('studio.automation.flow', 'automation_id', string="Flujo de Studio Pro")


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    studio_app_id = fields.Many2one('studio.app', string="App de Studio Pro", ondelete='set null', index=True)


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    def studio_get_field_lines(self):
        """Return the ordered list of editable rows (mostly <field/> nodes)
        found in this view's arch, each described by a precise xpath so they
        can later be reordered / edited / removed reliably.
        """
        self.ensure_one()
        if not self.arch:
            return []
        try:
            tree = etree.fromstring(self.arch.encode('utf-8'))
        except etree.XMLSyntaxError as e:
            raise UserError(self.env._("No se pudo interpretar el arch de esta vista: %s") % e)

        root_tree = tree.getroottree()
        lines = []
        for node in tree.iter():
            if node.tag != 'field':
                continue
            name = node.get('name')
            if not name or name in _SKIP_FIELD_NAMES:
                continue
            # skip fields nested inside another field (e.g. one2many sub-views)
            parent = node.getparent()
            skip = False
            anc = parent
            while anc is not None:
                if anc.tag == 'field':
                    skip = True
                    break
                anc = anc.getparent()
            if skip:
                continue
            field = self.env['ir.model.fields'].sudo().search(
                [('model', '=', self.model), ('name', '=', name)], limit=1)
            lines.append({
                'xpath': root_tree.getpath(node),
                'parent_xpath': root_tree.getpath(parent) if parent is not None else '',
                'name': name,
                'string': node.get('string') or (field.field_description if field else name),
                'ttype': field.ttype if field else '',
                'required': node.get('required') == '1' or node.get('required') == 'True',
                'readonly': node.get('readonly') == '1' or node.get('readonly') == 'True',
                'invisible': bool(node.get('invisible')) and node.get('invisible') not in ('0', 'False'),
                'optional': node.get('optional') or '',
                'widget': node.get('widget') or '',
            })
        return lines

    def studio_move_field(self, xpath, direction):
        """Move the <field> node at ``xpath`` up or down among its siblings
        that share the same parent (native drag & drop across different
        groups/pages is intentionally not supported to avoid corrupting the
        layout — use the 'Add field' action to place it in another group).
        """
        self.ensure_one()
        tree = etree.fromstring(self.arch.encode('utf-8'))
        node = tree.getroottree().xpath(xpath)
        if not node:
            raise UserError(self.env._("No se encontró el elemento, por favor actualiza la página."))
        node = node[0]
        parent = node.getparent()
        if parent is None:
            return False
        siblings = list(parent)
        idx = siblings.index(node)
        if direction == 'up' and idx > 0:
            parent.remove(node)
            parent.insert(idx - 1, node)
        elif direction == 'down' and idx < len(siblings) - 1:
            parent.remove(node)
            parent.insert(idx + 1, node)
        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return True

    def studio_remove_field(self, xpath):
        self.ensure_one()
        tree = etree.fromstring(self.arch.encode('utf-8'))
        nodes = tree.getroottree().xpath(xpath)
        if not nodes:
            raise UserError(self.env._("No se encontró el elemento, por favor actualiza la página."))
        node = nodes[0]
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return True

    def studio_set_field_attrs(self, xpath, values):
        """``values`` is a dict of attribute -> python value (bool/str) to
        set (or clear, when falsy) on the node at ``xpath``.
        """
        self.ensure_one()
        tree = etree.fromstring(self.arch.encode('utf-8'))
        nodes = tree.getroottree().xpath(xpath)
        if not nodes:
            raise UserError(self.env._("No se encontró el elemento, por favor actualiza la página."))
        node = nodes[0]
        for attr, value in values.items():
            if not value:
                if attr in node.attrib:
                    del node.attrib[attr]
                continue
            if isinstance(value, bool):
                node.set(attr, '1')
            else:
                node.set(attr, str(value))
        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return True

    def studio_apply_field_lines(self, lines):
        """Apply a full re-ordering/edit/removal/re-parenting pass in one
        shot, given ``lines``: an ordered list of dicts with keys ``xpath``
        (falsy for a brand new field), ``name``, ``parent_xpath`` (which
        group/page/root to place it in — '' means "pick automatically"),
        ``required``, ``readonly``, ``invisible``. Any existing field node
        whose xpath is *not* present in ``lines`` is removed.

        Every node — existing or new — is (re-)resolved to its target
        container up front from the original, unmodified tree before any
        mutation happens, so moving one field into a different group can
        never invalidate another field's own xpath or target — the classic
        pitfall of re-using positional xpaths after a structural change.
        """
        self.ensure_one()
        tree = etree.fromstring(self.arch.encode('utf-8'))
        root_tree = tree.getroottree()

        existing = {}
        for node in tree.iter('field'):
            existing[root_tree.getpath(node)] = node

        def resolve_container(parent_xpath):
            if parent_xpath:
                found = root_tree.xpath(parent_xpath)
                if found:
                    return found[0]
            fallback = tree.find('.//sheet/group') if tree.tag == 'form' else tree.find('.//group')
            if fallback is None:
                fallback = tree.find('.//sheet') if tree.tag == 'form' else tree
            return fallback

        wanted_xpaths = {l['xpath'] for l in lines if l.get('xpath')}
        for xpath, node in list(existing.items()):
            if xpath not in wanted_xpaths:
                parent = node.getparent()
                if parent is not None:
                    parent.remove(node)

        last_node_by_parent = {}
        for line in lines:
            xpath = line.get('xpath')
            target_parent = resolve_container(line.get('parent_xpath'))
            if xpath and xpath in existing:
                node = existing[xpath]
            else:
                node = etree.Element('field', name=line['name'])

            for attr in ('required', 'readonly', 'invisible'):
                value = line.get(attr)
                if value:
                    node.set(attr, '1')
                elif attr in node.attrib:
                    del node.attrib[attr]

            # append()/addnext() both auto-detach the node from wherever it
            # currently lives (including a different group/page), so this
            # handles re-parenting and re-ordering in one uniform step.
            ref = last_node_by_parent.get(id(target_parent))
            if ref is not None:
                ref.addnext(node)
            else:
                target_parent.append(node)
            last_node_by_parent[id(target_parent)] = node

        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return True

    def studio_pro_get_designer_data(self):
        """Everything the drag-and-drop visual designer needs for this view
        in one call: the current field lines (same shape/order as
        ``studio_get_field_lines``), the containers they can be dropped
        into, and the model's remaining fields, ready to be dragged in from
        the designer's toolbar."""
        self.ensure_one()
        if not self.env.user.has_group('studio_pro.group_studio_manager'):
            raise UserError(self.env._("No tenés permiso para usar Studio Pro."))
        lines = self.studio_get_field_lines()
        used_names = {l['name'] for l in lines}
        model = self.env['ir.model'].sudo().search([('model', '=', self.model)], limit=1)
        available_fields = [{
            'name': f.name, 'string': f.field_description or f.name, 'ttype': f.ttype,
        } for f in model.field_id.sorted('field_description')
            if f.name not in used_names and f.name not in _SKIP_FIELD_NAMES]
        return {
            'view_id': self.id,
            'view_name': self.name,
            'model': self.model,
            'model_name': model.name,
            'lines': lines,
            'containers': self.studio_get_containers(),
            'available_fields': available_fields,
        }

    def studio_pro_apply_designer_lines(self, lines):
        """Save a full pass from the visual designer and log it, then return
        the freshly re-read field lines so newly-created nodes (sent without
        an xpath) come back with the real one — letting the designer keep
        working on the same screen without a full reload."""
        self.ensure_one()
        if not self.env.user.has_group('studio_pro.group_studio_manager'):
            raise UserError(self.env._("No tenés permiso para usar Studio Pro."))
        self.studio_apply_field_lines(lines)
        self.env['studio.change'].log(
            'view', 'ir.ui.view', self.id, action='update',
            summary="Diseño de la vista #%s (%s) editado con el diseñador visual (arrastrar y soltar)"
                    % (self.id, self.model))
        return self.studio_get_field_lines()

    def studio_get_containers(self):
        """Returns the list of places a field (or another container) can be
        placed into: the root/sheet itself, plus every existing <group> and
        <page> (notebook tab), each with a human-readable label and its
        xpath. Used to populate the "place it in" dropdown in the view
        designer — this is what turns the editor from "one flat list of
        fields" into something that understands real form layout."""
        self.ensure_one()
        if not self.arch:
            return [{'xpath': '', 'label': '(Nivel principal)'}]
        tree = etree.fromstring(self.arch.encode('utf-8'))
        root_tree = tree.getroottree()
        containers = [{'xpath': '', 'label': '(Nivel principal / automático)'}]
        for node in tree.iter():
            if node.tag == 'group':
                containers.append({
                    'xpath': root_tree.getpath(node),
                    'label': 'Grupo: %s' % (node.get('string') or '(sin título)'),
                })
            elif node.tag == 'page':
                containers.append({
                    'xpath': root_tree.getpath(node),
                    'label': 'Pestaña: %s' % (node.get('string') or '(sin título)'),
                })
        return containers

    def studio_add_group(self, string=False, parent_xpath=False):
        """Adds a new, empty <group> — a section of the form — either inside
        ``parent_xpath`` (e.g. a notebook page) or at the end of the
        <sheet>/root. Returns the new group's xpath, ready to be used as a
        target container for fields."""
        self.ensure_one()
        tree = etree.fromstring(self.arch.encode('utf-8'))
        new_group = etree.Element('group')
        if string:
            new_group.set('string', string)
        parent = None
        if parent_xpath:
            found = tree.getroottree().xpath(parent_xpath)
            parent = found[0] if found else None
        if parent is None:
            parent = tree.find('.//sheet') if tree.tag == 'form' else tree
        parent.append(new_group)
        xpath = tree.getroottree().getpath(new_group)
        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return xpath

    def studio_add_page(self, string):
        """Adds a new notebook tab (creating the <notebook> itself if the
        form doesn't have one yet), with one empty group inside it so
        fields have somewhere to land right away. Returns that group's
        xpath."""
        self.ensure_one()
        tree = etree.fromstring(self.arch.encode('utf-8'))
        notebook = tree.find('.//notebook')
        if notebook is None:
            sheet = tree.find('.//sheet') if tree.tag == 'form' else tree
            notebook = etree.SubElement(sheet, 'notebook')
        new_page = etree.SubElement(notebook, 'page')
        new_page.set('string', string or 'Nueva Pestaña')
        new_group = etree.SubElement(new_page, 'group')
        xpath = tree.getroottree().getpath(new_group)
        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return xpath

    @api.model
    def studio_create_view(self, model_name, view_type, name=False):
        """Creates a brand-new, minimal-but-valid view of ``view_type``
        ('form', 'list', 'kanban', 'search', 'calendar', 'pivot', 'graph' or
        'activity') for ``model_name``, so Studio Pro can add views a model
        doesn't have yet — not just edit ones that already exist.

        Nota de honestidad: NO se ofrece 'gantt'. El renderizador de la vista
        Gantt (el módulo ``web_gantt``) es exclusivo de Odoo Enterprise — no
        existe en Community. Crear un ``ir.ui.view`` de tipo 'gantt' acá no
        rompería nada al guardar, pero al abrirlo el cliente no tendría con
        qué dibujarlo; ofrecer ese botón sería fingir una función de
        Enterprise que en los hechos no funcionaría, así que no está."""
        model = self.env['ir.model'].sudo().search([('model', '=', model_name)], limit=1)
        if not model:
            raise UserError(self.env._("Modelo '%s' no encontrado.") % model_name)
        name_field = 'x_name' if 'x_name' in self.env[model_name]._fields else 'display_name'

        if view_type == 'form':
            arch = '<form><sheet><group><field name="%s"/></group></sheet></form>' % name_field
        elif view_type == 'list':
            arch = '<list><field name="%s"/></list>' % name_field
        elif view_type == 'kanban':
            arch = (
                '<kanban><templates><t t-name="card">'
                '<div class="oe_kanban_global_click p-2">'
                '<field name="%s" class="fw-bold"/>'
                '</div>'
                '</t></templates></kanban>'
            ) % name_field
        elif view_type == 'search':
            arch = '<search><field name="%s"/></search>' % name_field
        elif view_type == 'calendar':
            date_field = next((f.name for f in model.field_id if f.ttype in ('date', 'datetime')), False)
            if not date_field:
                raise UserError(self.env._(
                    "Este modelo no tiene un campo de fecha/hora — agrega uno antes de crear una vista calendario."))
            arch = '<calendar date_start="%s"><field name="%s"/></calendar>' % (date_field, name_field)
        elif view_type == 'pivot':
            # Sin filas/columnas fijas: Odoo arma un pivot usable (cantidad de registros) desde
            # el vacío; el usuario elige medidas y agrupaciones desde la propia vista después.
            arch = '<pivot/>'
        elif view_type == 'graph':
            groupby_field = next((
                f.name for f in model.field_id
                if f.ttype in ('many2one', 'selection') and f.name != name_field
            ), False)
            arch = ('<graph><field name="%s"/></graph>' % groupby_field) if groupby_field else '<graph/>'
        elif view_type == 'activity':
            if not model.is_mail_activity:
                raise UserError(self.env._(
                    "Este modelo todavía no tiene 'Actividades' habilitadas — activalas primero "
                    "(botón 'Chatter y Actividades' en la App) antes de crear una vista Actividad."))
            arch = '<activity string="%s"><field name="%s"/><templates><div t-name="activity-box">' \
                   '<field name="%s" display="full"/></div></templates></activity>' % (
                       model.name, name_field, name_field)
        else:
            raise UserError(self.env._("Tipo de vista no soportado: %s") % view_type)

        view = self.sudo().create({
            'name': name or ('%s (Studio Pro %s)' % (model_name, view_type)),
            'type': view_type,
            'model': model_name,
            'arch': arch,
        })

        actions = self.env['ir.actions.act_window'].sudo().search([('res_model', '=', model_name)])
        for action in actions:
            modes = [m.strip() for m in (action.view_mode or '').split(',') if m.strip()]
            if view_type not in modes:
                modes.append(view_type)
                action.view_mode = ','.join(modes)

        return view

    @api.model
    def studio_pro_quick_edit_action(self, model_name, view_type=False):
        """Entry point for the Studio Pro systray icon ("Editar con Studio
        Pro"): given whatever the user is currently looking at (any model,
        any view type, on any installed app), open the right Studio Pro
        wizard for it — the guided view editor if a primary view of that
        type already exists, or the New View wizard (pre-filled) if not.
        This is what makes Studio Pro reachable from every app, the same
        way Odoo Studio's own pencil icon works, without a separate
        per-model action to configure.
        """
        if not self.env.user.has_group('studio_pro.group_studio_manager'):
            raise UserError(self.env._("No tenés permiso para usar Studio Pro."))
        model = self.env['ir.model'].sudo().search([('model', '=', model_name)], limit=1)
        if not model:
            raise UserError(self.env._("Modelo '%s' no encontrado.") % model_name)

        view_type = view_type or 'form'
        view_id = self.sudo().default_view(model_name, view_type)
        if not view_id:
            return {
                'type': 'ir.actions.act_window',
                'name': self.env._("Studio Pro — Nueva vista"),
                'res_model': 'studio.new.view.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_res_model_id': model.id,
                    'default_view_type': view_type,
                },
            }
        if view_type in ('form', 'list'):
            return self.studio_pro_designer_action(view_id)
        return {
            'type': 'ir.actions.act_window',
            'name': self.env._("Studio Pro — Editar vista"),
            'res_model': 'studio.view.editor.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_view_id': view_id},
        }

    @api.model
    def studio_pro_designer_action(self, view_id):
        """The client action descriptor that opens the drag-and-drop visual
        designer for ``view_id`` — shared by the systray icon and by the
        classic (list-based) editor's own "Diseño visual" button, so both
        entry points open the exact same screen."""
        return {
            'type': 'ir.actions.client',
            'tag': 'studio_pro_view_designer',
            'name': self.env._("Studio Pro — Diseño visual"),
            'target': 'current',
            'params': {'view_id': view_id},
        }

    def studio_insert_field(self, name, parent_xpath=False, after_xpath=False, groups=False):
        """Insert ``<field name="..."/>`` either right after ``after_xpath``
        (same parent), or as the last child of ``parent_xpath``, or — if
        neither is given — as the last field-holding node found (best
        effort), or finally as the last child of the view's <sheet>/root.

        ``groups``: optional comma-separated external ids (e.g.
        ``'base.group_system,sales_team.group_sale_manager'``). This is the
        real Odoo mechanism for field-level access: there is no ORM-level
        "field security" independent of the view for runtime-created fields
        (``ir.model.fields.groups`` is a known dead/unimplemented column in
        Odoo itself) — restricting the ``<field>`` node in every view that
        shows it, exactly like a hand-written module would with
        ``groups="..."`` on the field, is the correct and only way.
        """
        self.ensure_one()
        tree = etree.fromstring(self.arch.encode('utf-8'))
        new_node = etree.Element('field', name=name)
        if groups:
            new_node.set('groups', groups)

        if after_xpath:
            ref = tree.getroottree().xpath(after_xpath)
            if not ref:
                raise UserError(self.env._("No se encontró el elemento de referencia, por favor actualiza la página."))
            ref = ref[0]
            ref.addnext(new_node)
        elif parent_xpath:
            parent = tree.getroottree().xpath(parent_xpath)
            if not parent:
                raise UserError(self.env._("No se encontró el grupo de referencia, por favor actualiza la página."))
            parent[0].append(new_node)
        else:
            target = tree.find('.//sheet/group') if tree.tag == 'form' else None
            if target is None:
                target = tree.find('.//group')
            if target is None:
                target = tree.find('.//sheet')
            if target is None:
                target = tree
            target.append(new_node)

        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return True

    def studio_insert_filter(self, name, string, domain=False, context=False):
        """Agrega un ``<filter>`` (para un filtro con dominio fijo, o para un
        'Agrupar por' vía ``context``) directo bajo la raíz ``<search>`` —
        la sintaxis nativa de Odoo también acepta filtros sueltos sin
        envolverlos en un ``<group>``. No duplica si ya existe uno con el
        mismo ``name``."""
        self.ensure_one()
        if self.type != 'search':
            raise UserError(self.env._("Los filtros solo se pueden agregar a una vista de búsqueda."))
        tree = etree.fromstring(self.arch.encode('utf-8'))
        if tree.find(".//filter[@name='%s']" % name) is not None:
            return False
        node = etree.SubElement(tree, 'filter')
        node.set('name', name)
        node.set('string', string)
        if domain:
            node.set('domain', domain)
        if context:
            node.set('context', context)
        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return True

    def studio_add_chatter(self):
        """Agrega ``<chatter/>`` como último hijo del ``<form>`` raíz (al
        mismo nivel que ``<sheet/>``, nunca dentro), la sintaxis moderna de
        Odoo — usado al retrofitear Chatter/Actividades sobre un modelo de
        Studio Pro que ya tenía vistas de formulario creadas antes de
        activarlas."""
        self.ensure_one()
        if self.type != 'form':
            raise UserError(self.env._("El chatter solo se puede agregar a una vista de formulario."))
        tree = etree.fromstring(self.arch.encode('utf-8'))
        if tree.find('.//chatter') is not None:
            return False  # ya lo tiene, no duplicar
        etree.SubElement(tree, 'chatter')
        self.write({'arch': etree.tostring(tree, encoding='unicode')})
        return True
