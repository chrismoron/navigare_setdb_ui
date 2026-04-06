/** @odoo-module */
import { Component } from "@odoo/owl";
import { SetDBCubeCell } from "./cube_cell";

/**
 * SetDBCubeGrid — renders the OLAP pivot table.
 *
 * Expects the grid_data dict produced by setdb.cube.compute_grid() and
 * renders a full HTML table with:
 *   - corner cell, column headers, row headers
 *   - data cells with conditional heat-map colouring
 *   - total row / total column / grand total
 *   - formula rows with special styling
 *   - drill-down / roll-up expand indicators
 */
export class SetDBCubeGrid extends Component {
    static template = "setdb_ui.CubeGrid";
    static components = { SetDBCubeCell };
    static props = {
        grid_data: { type: Object },
        measures: { type: Array, optional: true },
        onDrillDown: { type: Function },
        onRollUp: { type: Function },
        showRowTotals: { type: Boolean, optional: true },
        showColTotals: { type: Boolean, optional: true },
        showGrandTotal: { type: Boolean, optional: true },
    };
    static defaultProps = {
        measures: [],
        showRowTotals: true,
        showColTotals: true,
        showGrandTotal: true,
    };

    get rows() {
        return this.props.grid_data.rows || [];
    }

    get columns() {
        return this.props.grid_data.columns || [];
    }

    get cells() {
        return this.props.grid_data.cells || {};
    }

    get rowTotals() {
        return this.props.grid_data.row_totals || {};
    }

    get colTotals() {
        return this.props.grid_data.col_totals || {};
    }

    get grandTotal() {
        return this.props.grid_data.grand_total || {};
    }

    get formulas() {
        return this.props.grid_data.formulas || {};
    }

    get formulaList() {
        return this.props.grid_data.formula_list || [];
    }

    get measureKey() {
        const measures = this.props.grid_data.measures || this.props.measures || [];
        return measures.length ? measures[0].key : null;
    }

    get hasData() {
        return this.rows.length > 0 && this.columns.length > 0;
    }

    // ------------------------------------------------------------------
    // Cell value helpers
    // ------------------------------------------------------------------

    cellValue(rowId, colId) {
        const key = `${rowId}_${colId}`;
        const cell = this.cells[key];
        if (!cell) {
            return null;
        }
        const mk = this.measureKey;
        return mk ? (cell[mk] ?? null) : null;
    }

    cellIntersectionCount(rowId, colId) {
        const key = `${rowId}_${colId}`;
        const cell = this.cells[key];
        return cell ? (cell._count ?? 0) : 0;
    }

    rowTotalValue(rowId) {
        const rt = this.rowTotals[rowId];
        if (!rt) return null;
        const mk = this.measureKey;
        return mk ? (rt[mk] ?? null) : null;
    }

    colTotalValue(colId) {
        const ct = this.colTotals[colId];
        if (!ct) return null;
        const mk = this.measureKey;
        return mk ? (ct[mk] ?? null) : null;
    }

    get grandTotalValue() {
        const mk = this.measureKey;
        return mk ? (this.grandTotal[mk] ?? null) : null;
    }

    // ------------------------------------------------------------------
    // Heat-map intensity  (1..5, or "" when null)
    // ------------------------------------------------------------------

    heatClass(value) {
        if (value === null || value === undefined) {
            return "";
        }
        // Determine intensity relative to the range of all visible cell values
        const range = this._valueRange();
        if (range.max === range.min) {
            return "setdb-cell-heat-1";
        }
        const ratio = (value - range.min) / (range.max - range.min);
        const bucket = Math.min(5, Math.max(1, Math.ceil(ratio * 5)));
        return `setdb-cell-heat-${bucket}`;
    }

    _valueRange() {
        if (this.__cachedRange) {
            return this.__cachedRange;
        }
        let min = Infinity;
        let max = -Infinity;
        const mk = this.measureKey;
        if (mk) {
            for (const cell of Object.values(this.cells)) {
                const v = cell[mk];
                if (v !== null && v !== undefined) {
                    if (v < min) min = v;
                    if (v > max) max = v;
                }
            }
        }
        if (!isFinite(min)) {
            min = 0;
            max = 0;
        }
        this.__cachedRange = { min, max };
        return this.__cachedRange;
    }

    // ------------------------------------------------------------------
    // Depth / expand helpers
    // ------------------------------------------------------------------

    depthClass(depth) {
        if (depth >= 1 && depth <= 3) {
            return `setdb-cube-depth-${depth}`;
        }
        return depth > 3 ? "setdb-cube-depth-3" : "";
    }

    isExpandable(element) {
        return element.has_children && !element.is_expanded;
    }

    isExpanded(element) {
        return element.has_children && element.is_expanded;
    }

    expandClass(element) {
        if (this.isExpanded(element)) {
            return "setdb-cube-expandable setdb-cube-expanded";
        }
        if (this.isExpandable(element)) {
            return "setdb-cube-expandable";
        }
        return "";
    }

    // ------------------------------------------------------------------
    // Event handlers
    // ------------------------------------------------------------------

    onRowHeaderClick(row) {
        if (this.isExpandable(row)) {
            this.props.onDrillDown("row", row.id);
        } else if (this.isExpanded(row)) {
            this.props.onRollUp("row", row.id);
        }
    }

    onColHeaderClick(col) {
        if (this.isExpandable(col)) {
            this.props.onDrillDown("column", col.id);
        } else if (this.isExpanded(col)) {
            this.props.onRollUp("column", col.id);
        }
    }

    // ------------------------------------------------------------------
    // Formula helpers
    // ------------------------------------------------------------------

    formulaRowClass(formula) {
        let cls = "setdb-formula-row";
        if (formula.style === "bold") cls += " bold";
        if (formula.style === "separator") return "setdb-separator-row";
        return cls;
    }

    formulaValue(formulaId, contextId) {
        const fData = this.formulas[formulaId];
        return fData ? (fData[contextId] ?? null) : null;
    }
}
