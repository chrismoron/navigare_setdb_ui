/** @odoo-module */
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class SetDBQueryResults extends Component {
    static template = "setdb_ui.QueryResults";
    static props = {
        results: { type: Array },
        execution_time_ms: { type: Number },
        result_count: { type: Number },
    };

    setup() {
        this.actionService = useService("action");
        this.state = useState({
            sortColumn: null,
            sortDirection: "asc",
            page: 0,
            pageSize: 100,
        });
    }

    get columns() {
        if (!this.props.results || this.props.results.length === 0) return [];
        return Object.keys(this.props.results[0]);
    }

    get sortedResults() {
        const data = [...this.props.results];
        if (this.state.sortColumn) {
            const col = this.state.sortColumn;
            const dir = this.state.sortDirection === "asc" ? 1 : -1;
            data.sort((a, b) => {
                const va = a[col];
                const vb = b[col];
                if (va == null && vb == null) return 0;
                if (va == null) return dir;
                if (vb == null) return -dir;
                if (typeof va === "number" && typeof vb === "number") {
                    return (va - vb) * dir;
                }
                return String(va).localeCompare(String(vb)) * dir;
            });
        }
        return data;
    }

    get pagedResults() {
        const start = this.state.page * this.state.pageSize;
        return this.sortedResults.slice(start, start + this.state.pageSize);
    }

    get totalPages() {
        return Math.max(1, Math.ceil(this.props.results.length / this.state.pageSize));
    }

    get executionTimeFormatted() {
        const ms = this.props.execution_time_ms;
        if (ms < 1000) return `${ms.toFixed(1)} ms`;
        return `${(ms / 1000).toFixed(2)} s`;
    }

    sortBy(column) {
        if (this.state.sortColumn === column) {
            this.state.sortDirection = this.state.sortDirection === "asc" ? "desc" : "asc";
        } else {
            this.state.sortColumn = column;
            this.state.sortDirection = "asc";
        }
    }

    sortIcon(column) {
        if (this.state.sortColumn !== column) return "fa-sort";
        return this.state.sortDirection === "asc" ? "fa-sort-asc" : "fa-sort-desc";
    }

    prevPage() {
        if (this.state.page > 0) this.state.page--;
    }

    nextPage() {
        if (this.state.page < this.totalPages - 1) this.state.page++;
    }

    onRowClick(row) {
        if (row.id) {
            this.actionService.doAction({
                type: "ir.actions.act_window",
                res_model: "setdb.element",
                res_id: row.id,
                views: [[false, "form"]],
                target: "current",
            });
        }
    }

    getCellValue(row, col) {
        const val = row[col];
        if (val === null || val === undefined) return "";
        if (typeof val === "boolean") return val ? "True" : "False";
        return String(val);
    }
}
