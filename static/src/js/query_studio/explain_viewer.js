/** @odoo-module */
import { Component } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

export class SetDBExplainViewer extends Component {
    static template = "setdb_ui.ExplainViewer";
    static props = {
        plan_text: { type: String },
    };

    get planNodes() {
        const text = this.props.plan_text || "";
        if (!text.trim()) return [];
        const lines = text.split("\n");
        return lines.map((line) => {
            const stripped = line.replace(/^[\s|├└─│]+/, "");
            const indent = line.length - line.trimStart().length;
            const depth = Math.floor(indent / 2);
            // Detect node types for color coding
            let nodeType = "default";
            const lower = stripped.toLowerCase();
            if (lower.includes("union")) nodeType = "union";
            else if (lower.includes("intersect")) nodeType = "intersect";
            else if (lower.includes("difference") || lower.includes("complement")) nodeType = "difference";
            else if (lower.includes("flatten") || lower.includes("members")) nodeType = "traverse";
            else if (lower.includes("ref") || lower.includes("element")) nodeType = "ref";
            else if (lower.includes("find") || lower.includes("filter")) nodeType = "filter";
            else if (lower.includes("optimized") || lower.includes("cached")) nodeType = "optimized";

            return { text: stripped, depth, nodeType, raw: line };
        });
    }

    getNodeStyle(node) {
        return `padding-left: ${node.depth * 24}px`;
    }

    getNodeClass(node) {
        return `setdb-explain-node setdb-explain-${node.nodeType}`;
    }

    getNodeIcon(node) {
        const icons = {
            union: "fa-object-ungroup",
            intersect: "fa-object-group",
            difference: "fa-minus-circle",
            traverse: "fa-sitemap",
            ref: "fa-cube",
            filter: "fa-filter",
            optimized: "fa-bolt",
            default: "fa-circle-o",
        };
        return icons[node.nodeType] || "fa-circle-o";
    }
}
