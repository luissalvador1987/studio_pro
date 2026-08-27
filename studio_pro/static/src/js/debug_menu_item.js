/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";

const debugRegistry = registry.category("debug");

/** Adds an "Edit with Studio Pro" entry next to the core "View: Form" /
 * "View: List" debug items, opening our structural field editor prefilled
 * with the view currently on screen. */
function editWithStudioPro({ accessRights, component, env }) {
    if (!accessRights.canEditView) {
        return null;
    }
    const { viewId, viewType: type } = component.env.config;
    if (!type || !["form", "list"].includes(type)) {
        return null;
    }
    return {
        type: "item",
        description: _t("Editar con Studio Pro"),
        callback: () => {
            env.services.action.doAction("studio_pro.action_studio_view_editor_wizard", {
                additionalContext: { default_view_id: viewId },
            });
        },
        sequence: 245,
        section: "ui",
    };
}

debugRegistry.category("view").add("studioPro.editWithStudioPro", editWithStudioPro);
