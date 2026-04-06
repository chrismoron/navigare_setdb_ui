/** @odoo-module */
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class SetDBSuggestion extends Component {
    static template = "setdb_ui.Suggestion";
    static props = {
        query: { type: String, optional: true },
        action_json: { type: String, optional: true },
        onApply: { type: Function },
    };

    get hasQuery() {
        return !!this.props.query;
    }

    get hasAction() {
        return !!this.props.action_json;
    }

    get displayQuery() {
        return this.props.query || "";
    }

    get actionLabel() {
        if (!this.props.action_json) return "";
        try {
            const action = JSON.parse(this.props.action_json);
            return action.label || action.action || _t("Apply Action");
        } catch {
            return _t("Apply Action");
        }
    }

    onApplyClick() {
        this.props.onApply(this.props.query || "", this.props.action_json || "");
    }

    onCopyClick() {
        if (this.props.query && navigator.clipboard) {
            navigator.clipboard.writeText(this.props.query);
        }
    }
}
