/** @odoo-module */
import { Component, useState, useRef, onMounted, onWillUpdateProps } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

const NODE_WIDTH = 150;
const NODE_HEIGHT = 40;
const LEVEL_GAP_Y = 80;
const NODE_GAP_X = 30;

const TYPE_COLORS = {
    primitive: { fill: "#e8f5e9", stroke: "#4caf50" },
    set: { fill: "#e3f2fd", stroke: "#1976d2" },
    sequence: { fill: "#fff3e0", stroke: "#ff9800" },
};

export class SetDBDagCanvas extends Component {
    static template = "setdb_ui.DagCanvas";
    static props = {
        elements: { type: Array },
        edges: { type: Array },
        onSelectElement: { type: Function },
        onCreateEdge: { type: Function },
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.state = useState({
            nodes: [],
            edgePaths: [],
            viewBox: "0 0 1200 600",
            connecting_from: null,
        });

        onMounted(() => {
            this._layoutNodes();
        });

        onWillUpdateProps((nextProps) => {
            // Schedule re-layout after props update
            this._layoutNodesFromProps(nextProps.elements, nextProps.edges);
        });
    }

    // ------------------------------------------------------------------
    // Layout
    // ------------------------------------------------------------------

    _layoutNodes() {
        this._layoutNodesFromProps(this.props.elements, this.props.edges);
    }

    _layoutNodesFromProps(elements, edges) {
        if (!elements || elements.length === 0) {
            this.state.nodes = [];
            this.state.edgePaths = [];
            return;
        }

        // Build adjacency: parent -> [child_ids]
        const childrenMap = {};
        const parentSet = new Set();
        for (const e of edges) {
            if (!childrenMap[e.parent_id]) {
                childrenMap[e.parent_id] = [];
            }
            childrenMap[e.parent_id].push(e.child_id);
            parentSet.add(e.child_id);
        }

        // Roots are elements that are never children
        const elementById = {};
        for (const el of elements) {
            elementById[el.id] = el;
        }
        const roots = elements.filter((el) => !parentSet.has(el.id));

        // BFS to assign levels
        const levelMap = {};
        const visited = new Set();
        const queue = roots.map((r) => ({ id: r.id, level: 0 }));
        for (const item of queue) {
            visited.add(item.id);
        }
        while (queue.length) {
            const { id, level } = queue.shift();
            levelMap[id] = Math.max(levelMap[id] || 0, level);
            const kids = childrenMap[id] || [];
            for (const kid of kids) {
                if (!visited.has(kid)) {
                    visited.add(kid);
                    queue.push({ id: kid, level: level + 1 });
                }
            }
        }

        // Handle orphan elements (not connected via edges)
        for (const el of elements) {
            if (levelMap[el.id] === undefined) {
                levelMap[el.id] = 0;
            }
        }

        // Group by level
        const levels = {};
        for (const [idStr, level] of Object.entries(levelMap)) {
            if (!levels[level]) levels[level] = [];
            levels[level].push(Number(idStr));
        }

        // Assign positions
        const positions = {};
        const maxLevel = Math.max(...Object.keys(levels).map(Number), 0);
        let maxX = 0;

        for (let lvl = 0; lvl <= maxLevel; lvl++) {
            const ids = levels[lvl] || [];
            const totalWidth = ids.length * NODE_WIDTH + (ids.length - 1) * NODE_GAP_X;
            let startX = 20;
            const y = 40 + lvl * LEVEL_GAP_Y;
            for (let i = 0; i < ids.length; i++) {
                const x = startX + i * (NODE_WIDTH + NODE_GAP_X);
                positions[ids[i]] = { x, y };
                if (x + NODE_WIDTH > maxX) maxX = x + NODE_WIDTH;
            }
        }

        // Build node data
        const nodes = elements
            .filter((el) => positions[el.id])
            .map((el) => {
                const pos = positions[el.id];
                const colors = TYPE_COLORS[el.element_type] || TYPE_COLORS.primitive;
                return {
                    id: el.id,
                    name: el.name,
                    element_type: el.element_type,
                    x: pos.x,
                    y: pos.y,
                    width: NODE_WIDTH,
                    height: NODE_HEIGHT,
                    fill: colors.fill,
                    stroke: colors.stroke,
                    textX: pos.x + NODE_WIDTH / 2,
                    textY: pos.y + NODE_HEIGHT / 2,
                    label: el.name.length > 16 ? el.name.substring(0, 14) + ".." : el.name,
                };
            });

        // Build edge paths
        const edgePaths = edges
            .filter((e) => positions[e.parent_id] && positions[e.child_id])
            .map((e) => {
                const pPos = positions[e.parent_id];
                const cPos = positions[e.child_id];
                const x1 = pPos.x + NODE_WIDTH / 2;
                const y1 = pPos.y + NODE_HEIGHT;
                const x2 = cPos.x + NODE_WIDTH / 2;
                const y2 = cPos.y;
                const midY = (y1 + y2) / 2;
                return {
                    id: e.id,
                    d: `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`,
                    parent_id: e.parent_id,
                    child_id: e.child_id,
                };
            });

        const totalHeight = 40 + (maxLevel + 1) * LEVEL_GAP_Y + NODE_HEIGHT + 40;
        const totalWidth = Math.max(maxX + 40, 800);
        this.state.viewBox = `0 0 ${totalWidth} ${totalHeight}`;
        this.state.nodes = nodes;
        this.state.edgePaths = edgePaths;
    }

    // ------------------------------------------------------------------
    // Interaction
    // ------------------------------------------------------------------

    onNodeClick(ev, node) {
        ev.stopPropagation();
        if (this.state.connecting_from !== null) {
            // Complete edge creation
            this.props.onCreateEdge(this.state.connecting_from, node.id);
            this.state.connecting_from = null;
        } else {
            const element = this.props.elements.find((e) => e.id === node.id);
            if (element) {
                this.props.onSelectElement(element);
            }
        }
    }

    onNodeDblClick(ev, node) {
        ev.stopPropagation();
        // Start connecting mode
        this.state.connecting_from = node.id;
    }

    onCanvasClick() {
        this.state.connecting_from = null;
    }

    get isConnecting() {
        return this.state.connecting_from !== null;
    }

    get connectingLabel() {
        if (!this.state.connecting_from) return "";
        const el = this.props.elements.find((e) => e.id === this.state.connecting_from);
        return el ? el.name : "";
    }
}
