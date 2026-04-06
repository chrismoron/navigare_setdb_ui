/** @odoo-module */
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * SetDBCubeToolbar — top toolbar for the Cube Explorer.
 *
 * Provides cube selector, pivot/refresh/export buttons.
 */
export class SetDBCubeToolbar extends Component {
    static template = "setdb_ui.CubeToolbar";
    static props = {
        cubes: { type: Array },
        selected_cube_id: { type: [Number, { value: false }] },
        onCubeChange: { type: Function },
        onPivot: { type: Function },
        onExport: { type: Function },
        onRefresh: { type: Function },
    };

    onCubeSelect(ev) {
        const cubeId = parseInt(ev.target.value, 10);
        if (cubeId) {
            this.props.onCubeChange(cubeId);
        }
    }

    onPivotClick() {
        this.props.onPivot();
    }

    onRefreshClick() {
        this.props.onRefresh();
    }

    onExportExcel() {
        this.props.onExport("xlsx");
    }

    onExportCSV() {
        this.props.onExport("csv");
    }
}
