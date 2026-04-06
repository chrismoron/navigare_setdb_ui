/** @odoo-module */
import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

const OPERATIONS = [
    { value: "UNION", label: "UNION", description: "Combine elements from multiple sets", minOperands: 2, maxOperands: 10 },
    { value: "INTERSECT", label: "INTERSECT", description: "Elements common to all sets", minOperands: 2, maxOperands: 10 },
    { value: "DIFFERENCE", label: "DIFFERENCE", description: "Elements in first set but not in second", minOperands: 2, maxOperands: 2 },
    { value: "SYMMETRIC_DIFF", label: "SYMMETRIC_DIFF", description: "Elements in either set but not both", minOperands: 2, maxOperands: 2 },
    { value: "COMPLEMENT", label: "COMPLEMENT", description: "Elements NOT in the set", minOperands: 1, maxOperands: 1 },
    { value: "FLATTEN", label: "FLATTEN", description: "Flatten nested set hierarchy", minOperands: 1, maxOperands: 1 },
    { value: "MEMBERS", label: "MEMBERS", description: "Direct members of a set", minOperands: 1, maxOperands: 1 },
    { value: "ANCESTORS", label: "ANCESTORS", description: "All ancestors of an element", minOperands: 1, maxOperands: 1 },
    { value: "REACHABLE", label: "REACHABLE", description: "All reachable elements", minOperands: 1, maxOperands: 1 },
    { value: "FIND", label: "FIND", description: "Search elements by pattern", minOperands: 0, maxOperands: 0, hasPattern: true },
];

export class SetDBQueryBuilder extends Component {
    static template = "setdb_ui.QueryBuilder";
    static props = {
        onQueryGenerated: { type: Function },
    };

    setup() {
        this.state = useState({
            operation: "UNION",
            operands: ["", ""],
            findPattern: "",
            findField: "name",
        });
    }

    get operations() {
        return OPERATIONS;
    }

    get selectedOp() {
        return OPERATIONS.find((o) => o.value === this.state.operation) || OPERATIONS[0];
    }

    get canAddOperand() {
        return this.state.operands.length < this.selectedOp.maxOperands;
    }

    get canRemoveOperand() {
        return this.state.operands.length > Math.max(this.selectedOp.minOperands, 1);
    }

    onOperationChange(ev) {
        const op = OPERATIONS.find((o) => o.value === ev.target.value);
        this.state.operation = ev.target.value;
        if (op) {
            // Adjust operand count
            if (op.hasPattern) {
                this.state.operands = [];
            } else if (this.state.operands.length < op.minOperands) {
                while (this.state.operands.length < op.minOperands) {
                    this.state.operands.push("");
                }
            } else if (this.state.operands.length > op.maxOperands) {
                this.state.operands = this.state.operands.slice(0, op.maxOperands);
            }
        }
    }

    onOperandChange(index, ev) {
        this.state.operands[index] = ev.target.value;
    }

    onPatternChange(ev) {
        this.state.findPattern = ev.target.value;
    }

    onFieldChange(ev) {
        this.state.findField = ev.target.value;
    }

    addOperand() {
        if (this.canAddOperand) {
            this.state.operands.push("");
        }
    }

    removeOperand(index) {
        if (this.canRemoveOperand) {
            this.state.operands.splice(index, 1);
        }
    }

    generateQuery() {
        const op = this.selectedOp;
        let query = "";

        if (op.hasPattern) {
            // FIND operation
            const pattern = this.state.findPattern.trim();
            if (!pattern) return;
            query = `FIND("${pattern}")`;
        } else if (op.maxOperands === 1) {
            // Unary operations
            const operand = this.state.operands[0]?.trim();
            if (!operand) return;
            query = `${op.value}(${operand})`;
        } else {
            // Binary / n-ary operations
            const validOperands = this.state.operands
                .map((o) => o.trim())
                .filter(Boolean);
            if (validOperands.length < op.minOperands) return;
            query = `${op.value}(${validOperands.join(", ")})`;
        }

        this.props.onQueryGenerated(query);
    }

    get isValid() {
        const op = this.selectedOp;
        if (op.hasPattern) {
            return this.state.findPattern.trim().length > 0;
        }
        const valid = this.state.operands.filter((o) => o.trim()).length;
        return valid >= op.minOperands;
    }

    get previewQuery() {
        const op = this.selectedOp;
        if (op.hasPattern) {
            const p = this.state.findPattern.trim() || "...";
            return `FIND("${p}")`;
        }
        if (op.maxOperands === 1) {
            const o = this.state.operands[0]?.trim() || "...";
            return `${op.value}(${o})`;
        }
        const ops = this.state.operands.map((o) => o.trim() || "...");
        return `${op.value}(${ops.join(", ")})`;
    }
}
