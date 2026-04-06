/** @odoo-module */
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

/**
 * SetDBMeasurePicker — dropdown to select which measure to display in the
 * OLAP grid.  Shows the aggregation type as a small badge next to the name.
 */
export class SetDBMeasurePicker extends Component {
    static template = "setdb_ui.MeasurePicker";
    static props = {
        measures: { type: Array },
        selected_measure_id: { type: [Number, { value: false }] },
        onMeasureChange: { type: Function },
    };

    /** Map aggregation code → short label for the badge. */
    static AGG_LABELS = {
        sum: "SUM",
        count: "CNT",
        avg: "AVG",
        min: "MIN",
        max: "MAX",
        count_distinct: "DST",
        median: "MED",
        variance: "VAR",
        stddev: "STD",
    };

    onMeasureSelect(ev) {
        const measureId = parseInt(ev.target.value, 10);
        if (measureId) {
            this.props.onMeasureChange(measureId);
        }
    }

    aggLabel(agg) {
        return SetDBMeasurePicker.AGG_LABELS[agg] || agg;
    }
}
