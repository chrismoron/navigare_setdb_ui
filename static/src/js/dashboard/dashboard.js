/** @odoo-module */
import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SetDBDashboard extends Component {
    static template = "setdb_ui.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            stats: {
                element_count: 0,
                edge_count: 0,
                cube_count: 0,
                query_count: 0,
                bridge_count: 0,
                hierarchy_count: 0,
                primitive_count: 0,
                set_count: 0,
                sequence_count: 0,
            },
            shortcuts: [],
            recent_queries: [],
            is_loading: false,
        });

        onMounted(() => {
            this.loadDashboard();
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async loadDashboard() {
        this.state.is_loading = true;
        try {
            await Promise.all([
                this._loadStats(),
                this._loadShortcuts(),
                this._loadRecentQueries(),
            ]);
        } catch (err) {
            this.notification.add(_t("Failed to load dashboard data."), { type: "danger" });
        } finally {
            this.state.is_loading = false;
        }
    }

    async _loadStats() {
        const [
            elementCount,
            edgeCount,
            cubeCount,
            queryCount,
            bridgeCount,
        ] = await Promise.all([
            this.orm.searchCount("setdb.element", [["active", "=", true]]),
            this.orm.searchCount("setdb.edge", []),
            this.orm.searchCount("setdb.cube", [["active", "=", true]]),
            this.orm.searchCount("setdb.saved.query", []),
            this.orm.searchCount("setdb.data.bridge", [["active", "=", true]]),
        ]);

        // Element type breakdown
        const [primitiveCount, setCount, sequenceCount] = await Promise.all([
            this.orm.searchCount("setdb.element", [
                ["active", "=", true],
                ["element_type", "=", "primitive"],
            ]),
            this.orm.searchCount("setdb.element", [
                ["active", "=", true],
                ["element_type", "=", "set"],
            ]),
            this.orm.searchCount("setdb.element", [
                ["active", "=", true],
                ["element_type", "=", "sequence"],
            ]),
        ]);

        let hierarchyCount = 0;
        try {
            hierarchyCount = await this.orm.searchCount("setdb.hierarchy", []);
        } catch {
            // Model may not exist in some configurations
        }

        this.state.stats = {
            element_count: elementCount,
            edge_count: edgeCount,
            cube_count: cubeCount,
            query_count: queryCount,
            bridge_count: bridgeCount,
            hierarchy_count: hierarchyCount,
            primitive_count: primitiveCount,
            set_count: setCount,
            sequence_count: sequenceCount,
        };
    }

    async _loadShortcuts() {
        try {
            const shortcuts = await this.orm.searchRead(
                "setdb.ui.shortcut",
                [["user_id", "=", false]],  // Will be filtered server-side to current user
                ["id", "name", "action_type", "target_id", "icon", "keyboard_shortcut"],
                { order: "sequence asc", limit: 10 }
            );
            this.state.shortcuts = shortcuts;
        } catch {
            // Shortcut loading is non-critical
            this.state.shortcuts = [];
        }
    }

    async _loadRecentQueries() {
        try {
            const queries = await this.orm.searchRead(
                "setdb.query.history",
                [],
                ["id", "query_text", "executed_at", "execution_time_ms", "result_count", "status"],
                { order: "executed_at desc", limit: 10 }
            );
            this.state.recent_queries = queries;
        } catch {
            this.state.recent_queries = [];
        }
    }

    // ------------------------------------------------------------------
    // Navigation actions
    // ------------------------------------------------------------------

    openEditorStudio() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "setdb_editor_studio",
            name: _t("Editor Studio"),
        });
    }

    openQueryStudio() {
        this.action.doAction({
            type: "ir.actions.client",
            tag: "setdb_query_studio",
            name: _t("Query Studio"),
        });
    }

    openCubeExplorer() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("OLAP Cubes"),
            res_model: "setdb.cube",
            view_mode: "list,form",
            target: "current",
        });
    }

    openBridges() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Data Bridges"),
            res_model: "setdb.data.bridge",
            view_mode: "list,form",
            target: "current",
        });
    }

    openElements() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Elements"),
            res_model: "setdb.element",
            view_mode: "list,form",
            target: "current",
        });
    }

    openSavedQueries() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: _t("Saved Queries"),
            res_model: "setdb.saved.query",
            view_mode: "list,form",
            target: "current",
        });
    }

    async executeShortcut(shortcut) {
        try {
            const result = await this.orm.call(
                "setdb.ui.shortcut",
                "action_execute",
                [shortcut.id]
            );
            if (result) {
                this.action.doAction(result);
            }
        } catch (err) {
            this.notification.add(_t("Failed to execute shortcut."), { type: "danger" });
        }
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    formatDate(dateStr) {
        if (!dateStr) return "";
        const d = new Date(dateStr);
        return d.toLocaleString();
    }

    formatMs(ms) {
        if (!ms) return "0ms";
        if (ms < 1000) return Math.round(ms) + "ms";
        return (ms / 1000).toFixed(2) + "s";
    }

    truncateQuery(text) {
        if (!text) return "";
        return text.length > 80 ? text.substring(0, 77) + "..." : text;
    }

    getStatusBadge(status) {
        return status === "success" ? "setdb-badge setdb-badge-success" : "setdb-badge setdb-badge-danger";
    }

    getShortcutIcon(shortcut) {
        return shortcut.icon || "fa-star";
    }

    get statCards() {
        const s = this.state.stats;
        return [
            { label: _t("Elements"), value: s.element_count, icon: "fa-cubes", color: "primary" },
            { label: _t("Edges"), value: s.edge_count, icon: "fa-project-diagram", color: "info" },
            { label: _t("Cubes"), value: s.cube_count, icon: "fa-th", color: "success" },
            { label: _t("Saved Queries"), value: s.query_count, icon: "fa-code", color: "warning" },
            { label: _t("Bridges"), value: s.bridge_count, icon: "fa-exchange-alt", color: "secondary" },
            { label: _t("Hierarchies"), value: s.hierarchy_count, icon: "fa-sitemap", color: "dark" },
        ];
    }

    get typeBreakdown() {
        const s = this.state.stats;
        return [
            { label: _t("Primitives"), value: s.primitive_count, cls: "setdb-badge-success" },
            { label: _t("Sets"), value: s.set_count, cls: "setdb-badge-info" },
            { label: _t("Sequences"), value: s.sequence_count, cls: "setdb-badge-warning" },
        ];
    }
}

registry.category("actions").add("setdb_dashboard", SetDBDashboard);
