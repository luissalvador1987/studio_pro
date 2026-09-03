/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { Layout } from "@web/search/layout";
import { getDefaultConfig } from "@web/views/view";
import { _t } from "@web/core/l10n/translation";

import { Component, useState, useSubEnv, onWillStart } from "@odoo/owl";

/**
 * Studio Pro's drag-and-drop visual designer for form/list views: a
 * lightweight wireframe of the view's groups/pages/fields, editable by
 * dragging — reorder a field by dragging it, move it to another
 * group/page by dropping it there, or drag a brand-new field in from the
 * "Campos disponibles" toolbar. "New Group"/"New Page" are plain buttons
 * (not draggable) — those create a *container*, a different kind of thing
 * than placing a field.
 *
 * This is a visual layer on top of the exact same backend the classic
 * (list-based) editor already uses: everything here is saved through
 * ``ir.ui.view.studio_apply_field_lines`` — no parallel persistence logic.
 *
 * Scope, honestly: only <field> nodes are draggable in this first version,
 * matching what the classic editor already supported — not buttons, labels,
 * or separators (the backend's node-creation is field-only for now, see
 * ``studio_apply_field_lines``). Kanban/calendar/pivot/graph/search views
 * don't have a real group/page layout to drag things into, so the systray
 * and wizard keep opening the classic editor for those.
 */
class StudioViewDesigner extends Component {
    static template = "studio_pro.StudioViewDesigner";
    static components = { Layout };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");
        useSetupAction();
        useSubEnv({
            config: {
                ...getDefaultConfig(),
                ...this.env.config,
            },
        });

        this.viewId = this.props.action.params.view_id;
        this.newLineCounter = 0;
        this.dragPayload = null;

        this.state = useState({
            loading: true,
            modelName: "",
            modelDisplayName: "",
            containers: [],
            availableFields: [],
            lines: [],
            dropIndicator: false,
            dirty: false,
            saving: false,
        });

        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        const data = await this.orm.call("ir.ui.view", "studio_pro_get_designer_data", [this.viewId]);
        this.state.modelName = data.model;
        this.state.modelDisplayName = data.model_name;
        this.state.containers = data.containers;
        this.state.availableFields = data.available_fields;
        this.state.lines = data.lines.map((l) => this._toLocalLine(l));
        this.state.dirty = false;
        this.state.loading = false;
    }

    _toLocalLine(l) {
        return {
            key: l.xpath,
            xpath: l.xpath,
            parent_xpath: l.parent_xpath || "",
            name: l.name,
            string: l.string,
            ttype: l.ttype,
            required: !!l.required,
            readonly: !!l.readonly,
            invisible: !!l.invisible,
        };
    }

    linesForContainer(xpath) {
        return this.state.lines.filter((l) => (l.parent_xpath || "") === (xpath || ""));
    }

    // ------------------------------------------------------------------
    // Drag & drop
    // ------------------------------------------------------------------
    onDragStartAvailable(ev, field) {
        this.dragPayload = { kind: "new", field };
        ev.dataTransfer.effectAllowed = "copy";
    }

    onDragStartLine(ev, line) {
        this.dragPayload = { kind: "existing", key: line.key };
        ev.dataTransfer.effectAllowed = "move";
    }

    onDragOverLine(ev, line) {
        ev.preventDefault();
        ev.stopPropagation();
        const rect = ev.currentTarget.getBoundingClientRect();
        const before = ev.clientY - rect.top < rect.height / 2;
        this.state.dropIndicator = { key: line.key, position: before ? "before" : "after" };
    }

    onDragLeaveLine() {
        this.state.dropIndicator = false;
    }

    onDropOnLine(ev, targetLine, containerXpath) {
        ev.preventDefault();
        ev.stopPropagation();
        const position = this.state.dropIndicator && this.state.dropIndicator.key === targetLine.key
            ? this.state.dropIndicator.position
            : "before";
        this._commitDrop(containerXpath, targetLine.key, position);
    }

    onDropOnContainer(ev, containerXpath) {
        ev.preventDefault();
        this._commitDrop(containerXpath, false, "after");
    }

    _commitDrop(containerXpath, targetKey, position) {
        const payload = this.dragPayload;
        this.dragPayload = null;
        this.state.dropIndicator = false;
        if (!payload) {
            return;
        }

        let movedLine;
        const lines = this.state.lines.slice();

        if (payload.kind === "existing") {
            const idx = lines.findIndex((l) => l.key === payload.key);
            if (idx === -1) {
                return;
            }
            [movedLine] = lines.splice(idx, 1);
            movedLine = { ...movedLine, parent_xpath: containerXpath || "" };
        } else {
            const field = payload.field;
            this.newLineCounter += 1;
            movedLine = {
                key: `new_${field.name}_${this.newLineCounter}`,
                xpath: false,
                parent_xpath: containerXpath || "",
                name: field.name,
                string: field.string,
                ttype: field.ttype,
                required: false,
                readonly: false,
                invisible: false,
            };
            this.state.availableFields = this.state.availableFields.filter((f) => f.name !== field.name);
        }

        let insertAt = lines.length;
        if (targetKey) {
            const targetIdx = lines.findIndex((l) => l.key === targetKey);
            if (targetIdx !== -1) {
                insertAt = position === "before" ? targetIdx : targetIdx + 1;
            }
        }
        lines.splice(insertAt, 0, movedLine);
        this.state.lines = lines;
        this.state.dirty = true;
    }

    removeLine(line) {
        this.state.lines = this.state.lines.filter((l) => l.key !== line.key);
        this.state.availableFields = [
            ...this.state.availableFields,
            { name: line.name, string: line.string, ttype: line.ttype },
        ].sort((a, b) => a.string.localeCompare(b.string));
        this.state.dirty = true;
    }

    toggleAttr(line, attr) {
        line[attr] = !line[attr];
        this.state.dirty = true;
    }

    // ------------------------------------------------------------------
    // Toolbar actions
    // ------------------------------------------------------------------
    async addContainer(kind) {
        const label = kind === "page" ? _t("Nueva pestaña") : _t("Nuevo grupo");
        const title = window.prompt(label + " — " + _t("título"), "");
        if (title === null) {
            return;
        }
        if (this.state.dirty) {
            await this.save({ silent: true });
        }
        const method = kind === "page" ? "studio_add_page" : "studio_add_group";
        await this.orm.call("ir.ui.view", method, [this.viewId, title || false]);
        await this.loadData();
    }

    async save(options = {}) {
        this.state.saving = true;
        try {
            const payload = this.state.lines.map((l) => ({
                xpath: l.xpath || false,
                parent_xpath: l.parent_xpath || "",
                name: l.name,
                required: l.required,
                readonly: l.readonly,
                invisible: l.invisible,
            }));
            const freshLines = await this.orm.call(
                "ir.ui.view",
                "studio_pro_apply_designer_lines",
                [this.viewId, payload]
            );
            this.state.lines = freshLines.map((l) => this._toLocalLine(l));
            this.state.dirty = false;
            if (!options.silent) {
                this.notification.add(_t("Cambios guardados."), { type: "success" });
            }
        } finally {
            this.state.saving = false;
        }
    }
}

registry.category("actions").add("studio_pro_view_designer", StudioViewDesigner);
