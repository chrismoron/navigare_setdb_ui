/** @odoo-module */
import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * SetDBDimensionPicker — lets the user assign hierarchies to rows, columns,
 * or filters by moving chips between three drop-zones via select dropdowns.
 */
export class SetDBDimensionPicker extends Component {
    static template = "setdb_ui.DimensionPicker";
    static props = {
        available_hierarchies: { type: Array },
        row_hierarchy: { type: [Object, { value: false }], optional: true },
        col_hierarchy: { type: [Object, { value: false }], optional: true },
        filter_hierarchies: { type: Array, optional: true },
        onRowChange: { type: Function },
        onColChange: { type: Function },
        onFilterChange: { type: Function },
    };
    static defaultProps = {
        filter_hierarchies: [],
    };

    setup() {
        this.state = useState({
            addFilterId: false,
        });
    }

    /** Hierarchies not currently assigned to any zone. */
    get unassigned() {
        const usedIds = new Set();
        if (this.props.row_hierarchy) {
            usedIds.add(this.props.row_hierarchy.id);
        }
        if (this.props.col_hierarchy) {
            usedIds.add(this.props.col_hierarchy.id);
        }
        for (const f of this.props.filter_hierarchies || []) {
            usedIds.add(f.id);
        }
        return (this.props.available_hierarchies || []).filter(
            (h) => !usedIds.has(h.id)
        );
    }

    onRowSelect(ev) {
        const id = parseInt(ev.target.value, 10);
        if (id) {
            const hier = this.props.available_hierarchies.find((h) => h.id === id);
            this.props.onRowChange(hier || false);
        }
    }

    onColSelect(ev) {
        const id = parseInt(ev.target.value, 10);
        if (id) {
            const hier = this.props.available_hierarchies.find((h) => h.id === id);
            this.props.onColChange(hier || false);
        }
    }

    onAddFilter(ev) {
        const id = parseInt(ev.target.value, 10);
        if (id) {
            const hier = this.props.available_hierarchies.find((h) => h.id === id);
            if (hier) {
                const current = [...(this.props.filter_hierarchies || []), hier];
                this.props.onFilterChange(current);
            }
            ev.target.value = "";
        }
    }

    removeFilter(hierId) {
        const current = (this.props.filter_hierarchies || []).filter(
            (h) => h.id !== hierId
        );
        this.props.onFilterChange(current);
    }

    clearRow() {
        this.props.onRowChange(false);
    }

    clearCol() {
        this.props.onColChange(false);
    }
}
