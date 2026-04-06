/** @odoo-module */
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class SetDBQueryHistory extends Component {
    static template = "setdb_ui.QueryHistory";
    static props = {
        history: { type: Array },
        onSelect: { type: Function },
    };

    formatTime(datetimeStr) {
        if (!datetimeStr) return "";
        try {
            const dt = new Date(datetimeStr);
            const now = new Date();
            const diffMs = now - dt;
            const diffMin = Math.floor(diffMs / 60000);
            if (diffMin < 1) return _t("just now");
            if (diffMin < 60) return `${diffMin}m ago`;
            const diffHr = Math.floor(diffMin / 60);
            if (diffHr < 24) return `${diffHr}h ago`;
            const diffDay = Math.floor(diffHr / 24);
            if (diffDay < 7) return `${diffDay}d ago`;
            return dt.toLocaleDateString();
        } catch {
            return datetimeStr;
        }
    }

    formatDuration(ms) {
        if (!ms && ms !== 0) return "";
        if (ms < 1000) return `${ms.toFixed(0)}ms`;
        return `${(ms / 1000).toFixed(1)}s`;
    }

    truncateQuery(text) {
        if (!text) return "";
        const line = text.split("\n")[0].trim();
        return line.length > 60 ? line.substring(0, 57) + "..." : line;
    }

    statusBadgeClass(status) {
        return status === "success" ? "badge bg-success" : "badge bg-danger";
    }

    onItemClick(item) {
        this.props.onSelect(item);
    }
}
