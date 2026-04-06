/** @odoo-module */
import { Component } from "@odoo/owl";

/**
 * SetDBCubeCell — renders a single data cell in the OLAP grid.
 *
 * Formats the numeric value according to format_string, applies conditional
 * formatting CSS class, and provides a tooltip with raw value details.
 */
export class SetDBCubeCell extends Component {
    static template = "setdb_ui.CubeCell";
    static props = {
        value: { type: Number, optional: true },
        format_string: { type: String, optional: true },
        conditional_format: { type: String, optional: true },
        intersection_count: { type: Number, optional: true },
    };
    static defaultProps = {
        value: 0,
        format_string: "#,##0.00",
        conditional_format: "",
        intersection_count: 0,
    };

    get formattedValue() {
        const val = this.props.value;
        if (val === null || val === undefined) {
            return "\u2014";
        }
        return this._applyFormat(val, this.props.format_string);
    }

    get heatClass() {
        return this.props.conditional_format || "";
    }

    get tooltipText() {
        const raw = this.props.value !== null && this.props.value !== undefined
            ? this.props.value
            : "N/A";
        const count = this.props.intersection_count || 0;
        return `Value: ${raw}\nIntersections: ${count}`;
    }

    /**
     * Simple number formatter supporting #,##0.00, #,##0, 0.00%, and plain
     * patterns.  Not a full Excel parser — covers common OLAP use-cases.
     */
    _applyFormat(value, fmt) {
        if (!fmt) {
            return String(value);
        }
        const isPercent = fmt.includes("%");
        let v = isPercent ? value * 100 : value;

        // Determine decimal places from the pattern
        const decimalMatch = fmt.match(/\.(0+)/);
        const decimals = decimalMatch ? decimalMatch[1].length : 0;

        // Use locale formatting for thousands separators
        const useGrouping = fmt.includes(",");
        const formatted = v.toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals,
            useGrouping,
        });
        return isPercent ? `${formatted}%` : formatted;
    }
}
