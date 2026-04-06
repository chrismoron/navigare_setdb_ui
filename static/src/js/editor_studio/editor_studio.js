/** @odoo-module */
import { Component, useState, onMounted } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { SetDBDagCanvas } from "./dag_canvas";
import { SetDBBulkImport } from "./bulk_import";
import { SetDBBridgeConfig } from "./bridge_config";

export class SetDBEditorStudio extends Component {
    static template = "setdb_ui.EditorStudio";
    static components = { SetDBDagCanvas, SetDBBulkImport, SetDBBridgeConfig };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            elements: [],
            edges: [],
            selected_element: null,
            is_loading: false,
            active_panel: "tree", // tree | import | bridges
            element_form: {
                name: "",
                element_type: "primitive",
                metadata_json: "{}",
            },
            search_query: "",
        });

        onMounted(() => {
            this.loadElements();
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async loadElements() {
        this.state.is_loading = true;
        try {
            const elements = await this.orm.searchRead(
                "setdb.element",
                [["active", "=", true]],
                ["id", "name", "element_type", "metadata_json", "created_at"],
                { order: "name asc", limit: 500 }
            );
            const edges = await this.orm.searchRead(
                "setdb.edge",
                [],
                ["id", "parent_id", "child_id", "ordinal"],
                { order: "ordinal asc" }
            );
            this.state.elements = elements;
            this.state.edges = edges.map((e) => ({
                id: e.id,
                parent_id: e.parent_id[0],
                child_id: e.child_id[0],
                ordinal: e.ordinal,
            }));
        } catch (err) {
            this.notification.add(_t("Failed to load elements: %s", err.message), {
                type: "danger",
            });
        } finally {
            this.state.is_loading = false;
        }
    }

    // ------------------------------------------------------------------
    // Element CRUD
    // ------------------------------------------------------------------

    async createElement(type) {
        const name = this.state.element_form.name.trim();
        if (!name) {
            this.notification.add(_t("Element name is required."), { type: "warning" });
            return;
        }
        this.state.is_loading = true;
        try {
            const id = await this.orm.create("setdb.element", [{
                name: name,
                element_type: type || this.state.element_form.element_type,
                metadata_json: this.state.element_form.metadata_json,
            }]);
            this.state.element_form.name = "";
            this.state.element_form.metadata_json = "{}";
            this.notification.add(_t("Element created."), { type: "success" });
            await this.loadElements();
            // Auto-select newly created element
            const newEl = this.state.elements.find((e) => e.id === id[0]);
            if (newEl) {
                this.state.selected_element = newEl;
            }
        } catch (err) {
            this.notification.add(_t("Create failed: %s", err.message), {
                type: "danger",
            });
        } finally {
            this.state.is_loading = false;
        }
    }

    async deleteElement(id) {
        if (!id) return;
        this.state.is_loading = true;
        try {
            await this.orm.unlink("setdb.element", [id]);
            if (this.state.selected_element && this.state.selected_element.id === id) {
                this.state.selected_element = null;
            }
            this.notification.add(_t("Element deleted."), { type: "success" });
            await this.loadElements();
        } catch (err) {
            this.notification.add(_t("Delete failed: %s", err.message), {
                type: "danger",
            });
        } finally {
            this.state.is_loading = false;
        }
    }

    async createEdge(parentId, childId) {
        if (!parentId || !childId) return;
        if (parentId === childId) {
            this.notification.add(_t("Cannot create self-referencing edge."), {
                type: "warning",
            });
            return;
        }
        this.state.is_loading = true;
        try {
            await this.orm.create("setdb.edge", [{
                parent_id: parentId,
                child_id: childId,
                ordinal: 0,
            }]);
            this.notification.add(_t("Edge created."), { type: "success" });
            await this.loadElements();
        } catch (err) {
            this.notification.add(_t("Edge creation failed: %s", err.message), {
                type: "danger",
            });
        } finally {
            this.state.is_loading = false;
        }
    }

    async deleteEdge(edgeId) {
        if (!edgeId) return;
        this.state.is_loading = true;
        try {
            await this.orm.unlink("setdb.edge", [edgeId]);
            this.notification.add(_t("Edge deleted."), { type: "success" });
            await this.loadElements();
        } catch (err) {
            this.notification.add(_t("Edge deletion failed: %s", err.message), {
                type: "danger",
            });
        } finally {
            this.state.is_loading = false;
        }
    }

    // ------------------------------------------------------------------
    // UI helpers
    // ------------------------------------------------------------------

    onSelectElement(element) {
        this.state.selected_element = element;
    }

    onCreateEdge(parentId, childId) {
        this.createEdge(parentId, childId);
    }

    setActivePanel(panel) {
        this.state.active_panel = panel;
    }

    onImportComplete() {
        this.state.active_panel = "tree";
        this.loadElements();
    }

    onBridgeSave() {
        this.notification.add(_t("Bridge configuration saved."), { type: "success" });
    }

    get filteredElements() {
        const q = this.state.search_query.toLowerCase();
        if (!q) return this.state.elements;
        return this.state.elements.filter(
            (el) => el.name.toLowerCase().includes(q)
        );
    }

    get rootElements() {
        const childIds = new Set(this.state.edges.map((e) => e.child_id));
        return this.filteredElements.filter((el) => !childIds.has(el.id));
    }

    getChildren(parentId) {
        const childIds = this.state.edges
            .filter((e) => e.parent_id === parentId)
            .map((e) => e.child_id);
        return this.state.elements.filter((el) => childIds.includes(el.id));
    }

    getElementTypeIcon(type) {
        switch (type) {
            case "primitive": return "fa-circle";
            case "set": return "fa-object-group";
            case "sequence": return "fa-list-ol";
            default: return "fa-question";
        }
    }

    getElementTypeBadge(type) {
        switch (type) {
            case "primitive": return "setdb-badge setdb-badge-success";
            case "set": return "setdb-badge setdb-badge-info";
            case "sequence": return "setdb-badge setdb-badge-warning";
            default: return "setdb-badge";
        }
    }

    async updateElement() {
        const el = this.state.selected_element;
        if (!el) return;
        try {
            await this.orm.write("setdb.element", [el.id], {
                name: el.name,
                element_type: el.element_type,
                metadata_json: el.metadata_json || "{}",
            });
            this.notification.add(_t("Element updated."), { type: "success" });
            await this.loadElements();
        } catch (err) {
            this.notification.add(_t("Update failed: %s", err.message), {
                type: "danger",
            });
        }
    }

    onFormNameInput(ev) {
        this.state.element_form.name = ev.target.value;
    }

    onFormTypeChange(ev) {
        this.state.element_form.element_type = ev.target.value;
    }

    onFormMetadataInput(ev) {
        this.state.element_form.metadata_json = ev.target.value;
    }

    onSearchInput(ev) {
        this.state.search_query = ev.target.value;
    }

    onSelectedNameInput(ev) {
        if (this.state.selected_element) {
            this.state.selected_element.name = ev.target.value;
        }
    }

    onSelectedTypeChange(ev) {
        if (this.state.selected_element) {
            this.state.selected_element.element_type = ev.target.value;
        }
    }

    onSelectedMetadataInput(ev) {
        if (this.state.selected_element) {
            this.state.selected_element.metadata_json = ev.target.value;
        }
    }
}

registry.category("actions").add("setdb_editor_studio", SetDBEditorStudio);
