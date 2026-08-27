/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

class StudioProSystrayItem extends Component {
    static template = "studio_pro.SystrayItem";
    static props = {};

    setup() {
        this.action = useService("action");
        this.state = useState({ allowed: false });
        onWillStart(async () => {
            this.state.allowed = await user.hasGroup("studio_pro.group_studio_manager");
        });
    }

    onClick() {
        this.action.doAction("studio_pro.action_studio_app");
    }
}

export const studioProSystrayItem = {
    Component: StudioProSystrayItem,
};

registry.category("systray").add("studio_pro.SystrayItem", studioProSystrayItem, { sequence: 1 });
