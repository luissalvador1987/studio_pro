/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService, useBus } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { router, routerBus } from "@web/core/browser/router";
import { _t } from "@web/core/l10n/translation";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";

/**
 * Studio Pro's navbar icon. Reachable from every installed App (not only
 * from inside the Studio Pro App itself):
 * - "Editar esta vista con Studio Pro" resolves whatever model/view type the
 *   URL currently points to and opens the right Studio Pro wizard for it —
 *   the guided view editor if a primary view of that type already exists,
 *   or the New View wizard (pre-filled) if not. Same idea as Odoo Studio's
 *   own toggle icon, without a per-model action to configure beforehand.
 * - "Abrir Studio Pro" is always available as a plain shortcut to the App.
 */
class StudioProSystrayItem extends Component {
    static template = "studio_pro.SystrayItem";
    static components = { Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ allowed: false });
        useBus(routerBus, "ROUTE_CHANGE", () => this.render());
        onWillStart(async () => {
            this.state.allowed = await user.hasGroup("studio_pro.group_studio_manager");
        });
    }

    get currentModel() {
        return router.current.model || false;
    }

    async onEditCurrentView() {
        const resModel = this.currentModel;
        if (!resModel) {
            this.notification.add(
                _t("Abrí una lista, kanban o formulario de alguna App para editarlo con Studio Pro."),
                { type: "warning" }
            );
            return;
        }
        const viewType = router.current.view_type || "form";
        const action = await this.orm.call("ir.ui.view", "studio_pro_quick_edit_action", [
            resModel,
            viewType,
        ]);
        this.action.doAction(action);
    }

    onOpenApp() {
        this.action.doAction("studio_pro.action_studio_app");
    }
}

export const studioProSystrayItem = {
    Component: StudioProSystrayItem,
};

registry.category("systray").add("studio_pro.SystrayItem", studioProSystrayItem, { sequence: 1 });
