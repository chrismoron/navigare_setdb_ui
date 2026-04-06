/** @odoo-module */
import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

import { SetDBQueryEditor } from "./query_editor";
import { SetDBQueryResults } from "./query_results";
import { SetDBExplainViewer } from "./explain_viewer";
import { SetDBQueryHistory } from "./query_history";
import { SetDBQueryBuilder } from "./query_builder";

export class SetDBQueryStudio extends Component {
    static template = "setdb_ui.QueryStudio";
    static components = {
        SetDBQueryEditor,
        SetDBQueryResults,
        SetDBExplainViewer,
        SetDBQueryHistory,
        SetDBQueryBuilder,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.actionService = useService("action");

        this.state = useState({
            query_text: "",
            results: [],
            execution_plan: "",
            is_loading: false,
            active_tab: "results", // results | explain | builder
            sidebar_tab: "saved", // saved | history
            saved_queries: [],
            history: [],
            execution_time_ms: 0,
            result_count: 0,
            error_message: "",
            save_dialog_open: false,
            save_name: "",
            save_description: "",
            selected_query_id: null,
        });

        onMounted(async () => {
            await Promise.all([
                this._loadSavedQueries(),
                this._loadHistory(),
            ]);
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async _loadSavedQueries() {
        try {
            const queries = await this.orm.searchRead(
                "setdb.saved.query",
                ["|", ["author_id", "=", false], ["author_id", "=", this.orm.user?.id || false],
                 "|", ["is_shared", "=", true], ["author_id", "=", this.orm.user?.id || false]],
                ["name", "query_text", "description", "tags", "last_executed", "execution_count", "avg_execution_time_ms"],
                { order: "name asc", limit: 200 }
            );
            this.state.saved_queries = queries;
        } catch {
            // Simplified fallback: load all accessible queries
            try {
                const queries = await this.orm.searchRead(
                    "setdb.saved.query",
                    [],
                    ["name", "query_text", "description", "tags", "last_executed", "execution_count", "avg_execution_time_ms"],
                    { order: "name asc", limit: 200 }
                );
                this.state.saved_queries = queries;
            } catch (err) {
                console.error("Failed to load saved queries:", err);
            }
        }
    }

    async _loadHistory() {
        try {
            const history = await this.orm.searchRead(
                "setdb.query.history",
                [],
                ["query_text", "executed_at", "execution_time_ms", "result_count", "status", "error_message"],
                { order: "executed_at desc", limit: 50 }
            );
            this.state.history = history;
        } catch (err) {
            console.error("Failed to load history:", err);
        }
    }

    // ------------------------------------------------------------------
    // Query execution
    // ------------------------------------------------------------------

    async executeQuery() {
        const query = this.state.query_text.trim();
        if (!query) {
            this.notification.add(_t("Please enter a query before executing."), {
                type: "warning",
            });
            return;
        }

        this.state.is_loading = true;
        this.state.error_message = "";
        this.state.active_tab = "results";

        try {
            const response = await this.orm.call(
                "setdb.query.executor",
                "execute",
                [query]
            );

            // The executor returns a recordset; we need to read data from it
            let results = [];
            let resultCount = 0;

            if (response && typeof response === "object") {
                if (Array.isArray(response)) {
                    results = response;
                    resultCount = response.length;
                } else if (response.ids) {
                    // It's a recordset reference - read the element data
                    const elementData = await this.orm.read(
                        "setdb.element",
                        response.ids,
                        ["name", "guid", "element_type", "display_name"],
                        {}
                    );
                    results = elementData;
                    resultCount = elementData.length;
                } else if (response.id) {
                    results = [response];
                    resultCount = 1;
                }
            }

            this.state.results = results;
            this.state.result_count = resultCount;
            // execution_time_ms is estimated client-side here; server could provide it
            this.notification.add(
                _t("%s result(s) returned.", resultCount),
                { type: "success" }
            );
        } catch (err) {
            const message = err.message || err.data?.message || String(err);
            this.state.error_message = message;
            this.state.results = [];
            this.state.result_count = 0;
            this.notification.add(
                _t("Query execution failed: %s", message),
                { type: "danger" }
            );
        } finally {
            this.state.is_loading = false;
            await this._loadHistory();
        }
    }

    async explainQuery() {
        const query = this.state.query_text.trim();
        if (!query) {
            this.notification.add(_t("Please enter a query to explain."), {
                type: "warning",
            });
            return;
        }

        this.state.is_loading = true;
        this.state.error_message = "";
        this.state.active_tab = "explain";

        try {
            const response = await this.orm.call(
                "setdb.query.executor",
                "parse_and_optimize",
                [query]
            );

            // Response is [raw_ast, optimized_ast] - render as text
            let planText = "";
            if (Array.isArray(response) && response.length >= 2) {
                planText = `=== Original AST ===\n${this._astToText(response[0])}\n\n=== Optimized AST ===\n${this._astToText(response[1])}`;
            } else if (typeof response === "string") {
                planText = response;
            } else {
                planText = JSON.stringify(response, null, 2);
            }

            this.state.execution_plan = planText;
        } catch (err) {
            const message = err.message || err.data?.message || String(err);
            this.state.error_message = message;
            this.state.execution_plan = "";
            this.notification.add(
                _t("Explain failed: %s", message),
                { type: "danger" }
            );
        } finally {
            this.state.is_loading = false;
        }
    }

    _astToText(ast, indent = 0) {
        if (!ast) return "  ".repeat(indent) + "(empty)";
        if (typeof ast === "string") return "  ".repeat(indent) + ast;
        if (typeof ast !== "object") return "  ".repeat(indent) + String(ast);

        const prefix = "  ".repeat(indent);
        const type = ast._type || ast.type || ast.constructor?.name || "Node";
        let lines = [`${prefix}${type}`];

        // Render known fields
        for (const [key, val] of Object.entries(ast)) {
            if (key.startsWith("_")) continue;
            if (key === "type") continue;
            if (Array.isArray(val)) {
                lines.push(`${prefix}  ${key}:`);
                for (const item of val) {
                    lines.push(this._astToText(item, indent + 2));
                }
            } else if (typeof val === "object" && val !== null) {
                lines.push(`${prefix}  ${key}:`);
                lines.push(this._astToText(val, indent + 2));
            } else {
                lines.push(`${prefix}  ${key}: ${val}`);
            }
        }
        return lines.join("\n");
    }

    // ------------------------------------------------------------------
    // Save / Load
    // ------------------------------------------------------------------

    openSaveDialog() {
        this.state.save_dialog_open = true;
        this.state.save_name = "";
        this.state.save_description = "";
    }

    closeSaveDialog() {
        this.state.save_dialog_open = false;
    }

    onSaveNameChange(ev) {
        this.state.save_name = ev.target.value;
    }

    onSaveDescriptionChange(ev) {
        this.state.save_description = ev.target.value;
    }

    async saveQuery() {
        const name = this.state.save_name.trim();
        const query = this.state.query_text.trim();

        if (!name) {
            this.notification.add(_t("Please enter a name for the query."), {
                type: "warning",
            });
            return;
        }
        if (!query) {
            this.notification.add(_t("Cannot save an empty query."), {
                type: "warning",
            });
            return;
        }

        try {
            if (this.state.selected_query_id) {
                // Update existing
                await this.orm.write("setdb.saved.query", [this.state.selected_query_id], {
                    name: name,
                    query_text: query,
                    description: this.state.save_description,
                });
                this.notification.add(_t("Query updated."), { type: "success" });
            } else {
                // Create new
                const id = await this.orm.create("setdb.saved.query", [{
                    name: name,
                    query_text: query,
                    description: this.state.save_description,
                }]);
                this.state.selected_query_id = Array.isArray(id) ? id[0] : id;
                this.notification.add(_t("Query saved."), { type: "success" });
            }
            this.state.save_dialog_open = false;
            await this._loadSavedQueries();
        } catch (err) {
            const message = err.message || err.data?.message || String(err);
            this.notification.add(
                _t("Failed to save query: %s", message),
                { type: "danger" }
            );
        }
    }

    async loadQuery(queryRecord) {
        this.state.query_text = queryRecord.query_text || "";
        this.state.selected_query_id = queryRecord.id;
        this.state.save_name = queryRecord.name || "";
        this.state.save_description = queryRecord.description || "";
        this.state.error_message = "";
        this.state.results = [];
        this.state.execution_plan = "";
    }

    async deleteQuery(queryId) {
        try {
            await this.orm.unlink("setdb.saved.query", [queryId]);
            if (this.state.selected_query_id === queryId) {
                this.state.selected_query_id = null;
                this.state.save_name = "";
            }
            this.notification.add(_t("Query deleted."), { type: "info" });
            await this._loadSavedQueries();
        } catch (err) {
            const message = err.message || err.data?.message || String(err);
            this.notification.add(
                _t("Failed to delete: %s", message),
                { type: "danger" }
            );
        }
    }

    // ------------------------------------------------------------------
    // UI event handlers
    // ------------------------------------------------------------------

    onQueryChange(value) {
        this.state.query_text = value;
    }

    onHistorySelect(item) {
        this.state.query_text = item.query_text || "";
        this.state.selected_query_id = null;
        this.state.error_message = "";
    }

    onQueryGenerated(queryText) {
        this.state.query_text = queryText;
        this.state.active_tab = "results";
    }

    setActiveTab(tab) {
        this.state.active_tab = tab;
    }

    setSidebarTab(tab) {
        this.state.sidebar_tab = tab;
    }

    clearEditor() {
        this.state.query_text = "";
        this.state.selected_query_id = null;
        this.state.save_name = "";
        this.state.error_message = "";
        this.state.results = [];
        this.state.execution_plan = "";
    }

    get hasUnsavedChanges() {
        if (!this.state.selected_query_id) return !!this.state.query_text.trim();
        const saved = this.state.saved_queries.find(
            (q) => q.id === this.state.selected_query_id
        );
        return saved && saved.query_text !== this.state.query_text;
    }

    get currentQueryName() {
        if (this.state.selected_query_id) {
            const saved = this.state.saved_queries.find(
                (q) => q.id === this.state.selected_query_id
            );
            return saved?.name || _t("Untitled");
        }
        return _t("New Query");
    }
}

registry.category("actions").add("setdb_query_studio", SetDBQueryStudio);
