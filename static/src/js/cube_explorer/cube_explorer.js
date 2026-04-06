/** @odoo-module */
import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

import { SetDBCubeGrid } from "./cube_grid";
import { SetDBCubeToolbar } from "./cube_toolbar";
import { SetDBDimensionPicker } from "./dimension_picker";
import { SetDBMeasurePicker } from "./measure_picker";

/**
 * SetDBCubeExplorer — main client action for the OLAP Cube Explorer.
 *
 * Orchestrates toolbar, dimension picker, measure picker and the pivot grid.
 * Communicates with the server via JSON-RPC endpoints defined in
 * setdb_ui/controllers/main.py.
 */
export class SetDBCubeExplorer extends Component {
    static template = "setdb_ui.CubeExplorer";
    static components = {
        SetDBCubeGrid,
        SetDBCubeToolbar,
        SetDBDimensionPicker,
        SetDBMeasurePicker,
    };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");

        this.state = useState({
            cube_id: false,
            grid_data: null,
            is_loading: false,
            available_cubes: [],
            available_hierarchies: [],
            selected_measures: [],
            selected_measure_id: false,
            row_hierarchy: false,
            col_hierarchy: false,
            filter_hierarchies: [],
            show_dimension_picker: false,
        });

        onMounted(async () => {
            await this.loadAvailableCubes();
            // If the action was opened with a specific cube in context, load it
            const context = this.props.action?.context || {};
            if (context.default_cube_id) {
                await this.onCubeChange(context.default_cube_id);
            }
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async loadAvailableCubes() {
        try {
            const result = await this.rpc("/web/dataset/call_kw", {
                model: "setdb.cube",
                method: "search_read",
                args: [[["active", "=", true]]],
                kwargs: {
                    fields: ["id", "name", "description"],
                    limit: 200,
                },
            });
            this.state.available_cubes = result || [];
        } catch (e) {
            this.notification.add(
                _t("Failed to load cubes: %s", e.message || e),
                { type: "danger" }
            );
        }
    }

    async loadGrid() {
        if (!this.state.cube_id) return;
        this.state.is_loading = true;
        try {
            const data = await this.rpc("/setdb_ui/cube/grid", {
                cube_id: this.state.cube_id,
            });
            if (data.error) {
                this.notification.add(data.error, { type: "danger" });
                return;
            }
            this.state.grid_data = data;
            this.state.selected_measures = data.measures || [];
            if (
                !this.state.selected_measure_id &&
                data.measures &&
                data.measures.length
            ) {
                this.state.selected_measure_id = data.measures[0].id;
            }
        } catch (e) {
            this.notification.add(
                _t("Failed to load grid: %s", e.message || e),
                { type: "danger" }
            );
        } finally {
            this.state.is_loading = false;
        }
    }

    async loadAvailableHierarchies() {
        try {
            const result = await this.rpc("/web/dataset/call_kw", {
                model: "setdb.hierarchy",
                method: "search_read",
                args: [[]],
                kwargs: {
                    fields: ["id", "name"],
                    limit: 500,
                },
            });
            this.state.available_hierarchies = result || [];
        } catch {
            // silently ignore — dimension picker just won't list anything
        }
    }

    // ------------------------------------------------------------------
    // Cube navigation
    // ------------------------------------------------------------------

    async drillDown(axis, elementId) {
        if (!this.state.cube_id) return;
        this.state.is_loading = true;
        try {
            const data = await this.rpc("/setdb_ui/cube/drill", {
                cube_id: this.state.cube_id,
                axis,
                element_id: elementId,
                direction: "down",
            });
            if (!data.error) {
                this.state.grid_data = data;
            }
        } catch (e) {
            this.notification.add(
                _t("Drill-down failed: %s", e.message || e),
                { type: "danger" }
            );
        } finally {
            this.state.is_loading = false;
        }
    }

    async rollUp(axis, elementId) {
        if (!this.state.cube_id) return;
        this.state.is_loading = true;
        try {
            const data = await this.rpc("/setdb_ui/cube/drill", {
                cube_id: this.state.cube_id,
                axis,
                element_id: elementId,
                direction: "up",
            });
            if (!data.error) {
                this.state.grid_data = data;
            }
        } catch (e) {
            this.notification.add(
                _t("Roll-up failed: %s", e.message || e),
                { type: "danger" }
            );
        } finally {
            this.state.is_loading = false;
        }
    }

    async pivotAxes() {
        if (!this.state.cube_id) return;
        this.state.is_loading = true;
        try {
            const data = await this.rpc("/setdb_ui/cube/pivot", {
                cube_id: this.state.cube_id,
            });
            if (!data.error) {
                this.state.grid_data = data;
            }
        } catch (e) {
            this.notification.add(
                _t("Pivot failed: %s", e.message || e),
                { type: "danger" }
            );
        } finally {
            this.state.is_loading = false;
        }
    }

    // ------------------------------------------------------------------
    // Export
    // ------------------------------------------------------------------

    exportGrid(format) {
        if (!this.state.cube_id) return;
        // Build a simple export by opening a download URL.
        // For now, produce a client-side CSV/TSV from the current grid_data.
        const data = this.state.grid_data;
        if (!data || !data.rows || !data.columns) return;

        const mk = data.measures && data.measures.length ? data.measures[0].key : null;
        const rows = data.rows;
        const cols = data.columns;
        const cells = data.cells || {};

        const lines = [];
        // Header row
        const header = [""].concat(cols.map((c) => c.name));
        lines.push(header.join("\t"));

        // Data rows
        for (const row of rows) {
            const vals = [row.name];
            for (const col of cols) {
                const cell = cells[`${row.id}_${col.id}`];
                const v = cell && mk ? (cell[mk] ?? "") : "";
                vals.push(v);
            }
            lines.push(vals.join("\t"));
        }

        const text = lines.join("\n");
        const mimeType = format === "csv" ? "text/csv" : "text/tab-separated-values";
        const ext = format === "csv" ? "csv" : "tsv";
        const blob = new Blob([text], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `cube_export.${ext}`;
        a.click();
        URL.revokeObjectURL(url);
    }

    // ------------------------------------------------------------------
    // Callbacks from child components
    // ------------------------------------------------------------------

    async onCubeChange(cubeId) {
        this.state.cube_id = cubeId;
        this.state.grid_data = null;
        this.state.selected_measure_id = false;
        await this.loadGrid();
    }

    onMeasureChange(measureId) {
        this.state.selected_measure_id = measureId;
    }

    toggleDimensionPicker() {
        this.state.show_dimension_picker = !this.state.show_dimension_picker;
        if (this.state.show_dimension_picker && !this.state.available_hierarchies.length) {
            this.loadAvailableHierarchies();
        }
    }

    async onRowHierarchyChange(hier) {
        this.state.row_hierarchy = hier;
        // Persist to server if a cube is selected
        if (this.state.cube_id && hier) {
            try {
                await this.rpc("/web/dataset/call_kw", {
                    model: "setdb.cube",
                    method: "write",
                    args: [[this.state.cube_id], { row_hierarchy_id: hier.id }],
                    kwargs: {},
                });
                await this.loadGrid();
            } catch {
                // ignore
            }
        }
    }

    async onColHierarchyChange(hier) {
        this.state.col_hierarchy = hier;
        if (this.state.cube_id && hier) {
            try {
                await this.rpc("/web/dataset/call_kw", {
                    model: "setdb.cube",
                    method: "write",
                    args: [[this.state.cube_id], { column_hierarchy_id: hier.id }],
                    kwargs: {},
                });
                await this.loadGrid();
            } catch {
                // ignore
            }
        }
    }

    async onFilterHierarchyChange(hiers) {
        this.state.filter_hierarchies = hiers;
        if (this.state.cube_id) {
            try {
                await this.rpc("/web/dataset/call_kw", {
                    model: "setdb.cube",
                    method: "write",
                    args: [
                        [this.state.cube_id],
                        { filter_hierarchy_ids: [[6, 0, hiers.map((h) => h.id)]] },
                    ],
                    kwargs: {},
                });
                await this.loadGrid();
            } catch {
                // ignore
            }
        }
    }
}

// Register as a client action
registry.category("actions").add("setdb_cube_explorer", SetDBCubeExplorer);
