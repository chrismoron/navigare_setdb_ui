/** @odoo-module */
import { Component, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const MAPPING_OPTIONS = [
    { value: "", label: "-- Skip --" },
    { value: "name", label: "Element Name" },
    { value: "element_type", label: "Element Type" },
    { value: "parent", label: "Parent Name" },
    { value: "metadata", label: "Metadata Key" },
];

export class SetDBBulkImport extends Component {
    static template = "setdb_ui.BulkImport";
    static props = {
        onImportComplete: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            file_data: null,
            file_name: "",
            columns: [],
            mapping: [],
            metadata_keys: [],
            preview_rows: [],
            all_rows: [],
            is_importing: false,
            import_progress: 0,
            import_stats: null,
        });
    }

    // ------------------------------------------------------------------
    // File handling
    // ------------------------------------------------------------------

    onFileChange(ev) {
        const file = ev.target.files[0];
        if (!file) return;
        this.state.file_name = file.name;

        const reader = new FileReader();
        reader.onload = (e) => {
            this._parseCSV(e.target.result);
        };
        reader.readAsText(file, "utf-8");
    }

    _parseCSV(text) {
        const lines = text.split(/\r?\n/).filter((l) => l.trim());
        if (lines.length < 2) {
            this.notification.add(_t("CSV must have a header row and at least one data row."), {
                type: "warning",
            });
            return;
        }

        const separator = this._detectSeparator(lines[0]);
        const columns = this._splitLine(lines[0], separator);
        const rows = [];
        for (let i = 1; i < lines.length; i++) {
            const cells = this._splitLine(lines[i], separator);
            if (cells.length > 0) {
                rows.push(cells);
            }
        }

        this.state.columns = columns;
        this.state.mapping = columns.map(() => "");
        this.state.metadata_keys = columns.map(() => "");
        this.state.preview_rows = rows.slice(0, 5);
        this.state.all_rows = rows;
        this.state.file_data = text;
        this.state.import_stats = null;

        // Auto-map columns by name
        for (let i = 0; i < columns.length; i++) {
            const col = columns[i].toLowerCase().trim();
            if (col === "name" || col === "element_name") {
                this.state.mapping[i] = "name";
            } else if (col === "type" || col === "element_type") {
                this.state.mapping[i] = "element_type";
            } else if (col === "parent" || col === "parent_name") {
                this.state.mapping[i] = "parent";
            }
        }
    }

    _detectSeparator(headerLine) {
        const commaCount = (headerLine.match(/,/g) || []).length;
        const semiCount = (headerLine.match(/;/g) || []).length;
        const tabCount = (headerLine.match(/\t/g) || []).length;
        if (tabCount >= commaCount && tabCount >= semiCount) return "\t";
        if (semiCount > commaCount) return ";";
        return ",";
    }

    _splitLine(line, sep) {
        // Simple CSV split handling quoted fields
        const result = [];
        let current = "";
        let inQuotes = false;
        for (let i = 0; i < line.length; i++) {
            const ch = line[i];
            if (ch === '"') {
                inQuotes = !inQuotes;
            } else if (ch === sep && !inQuotes) {
                result.push(current.trim());
                current = "";
            } else {
                current += ch;
            }
        }
        result.push(current.trim());
        return result;
    }

    // ------------------------------------------------------------------
    // Mapping
    // ------------------------------------------------------------------

    onMappingChange(ev, index) {
        this.state.mapping[index] = ev.target.value;
    }

    onMetadataKeyInput(ev, index) {
        this.state.metadata_keys[index] = ev.target.value;
    }

    get mappingOptions() {
        return MAPPING_OPTIONS;
    }

    get hasNameMapping() {
        return this.state.mapping.includes("name");
    }

    get totalRows() {
        return this.state.all_rows.length;
    }

    // ------------------------------------------------------------------
    // Import
    // ------------------------------------------------------------------

    async doImport() {
        if (!this.hasNameMapping) {
            this.notification.add(_t("You must map at least one column to 'Element Name'."), {
                type: "warning",
            });
            return;
        }

        this.state.is_importing = true;
        this.state.import_progress = 0;

        const mapping = this.state.mapping;
        const metaKeys = this.state.metadata_keys;
        const rows = this.state.all_rows;

        let created = 0;
        let skipped = 0;
        let errors = 0;

        // First pass: create all elements
        const elementNames = {};
        const toCreate = [];

        for (let i = 0; i < rows.length; i++) {
            const row = rows[i];
            let name = "";
            let elementType = "primitive";
            let metadata = {};

            for (let c = 0; c < mapping.length; c++) {
                const val = row[c] || "";
                switch (mapping[c]) {
                    case "name":
                        name = val;
                        break;
                    case "element_type":
                        elementType = ["primitive", "set", "sequence"].includes(val.toLowerCase())
                            ? val.toLowerCase()
                            : "primitive";
                        break;
                    case "metadata":
                        if (metaKeys[c] && val) {
                            metadata[metaKeys[c]] = val;
                        }
                        break;
                }
            }

            if (!name) {
                skipped++;
                continue;
            }

            toCreate.push({
                name,
                element_type: elementType,
                metadata_json: JSON.stringify(metadata),
                _parent_name: "",
            });

            // Capture parent name for second pass
            for (let c = 0; c < mapping.length; c++) {
                if (mapping[c] === "parent" && row[c]) {
                    toCreate[toCreate.length - 1]._parent_name = row[c].trim();
                }
            }
        }

        // Batch create elements
        try {
            const batchSize = 50;
            for (let b = 0; b < toCreate.length; b += batchSize) {
                const batch = toCreate.slice(b, b + batchSize);
                const vals = batch.map((item) => ({
                    name: item.name,
                    element_type: item.element_type,
                    metadata_json: item.metadata_json,
                }));
                const ids = await this.orm.create("setdb.element", vals);
                for (let j = 0; j < ids.length; j++) {
                    elementNames[batch[j].name] = ids[j];
                }
                created += ids.length;
                this.state.import_progress = Math.round(
                    ((b + batch.length) / toCreate.length) * 80
                );
            }
        } catch (err) {
            errors++;
            this.notification.add(_t("Import error: %s", err.message), {
                type: "danger",
            });
        }

        // Second pass: create edges for parent relationships
        const edgesToCreate = [];
        for (const item of toCreate) {
            if (item._parent_name && elementNames[item._parent_name] && elementNames[item.name]) {
                edgesToCreate.push({
                    parent_id: elementNames[item._parent_name],
                    child_id: elementNames[item.name],
                    ordinal: 0,
                });
            }
        }

        if (edgesToCreate.length > 0) {
            try {
                const batchSize = 50;
                for (let b = 0; b < edgesToCreate.length; b += batchSize) {
                    const batch = edgesToCreate.slice(b, b + batchSize);
                    await this.orm.create("setdb.edge", batch);
                    this.state.import_progress = 80 + Math.round(
                        ((b + batch.length) / edgesToCreate.length) * 20
                    );
                }
            } catch (err) {
                this.notification.add(_t("Edge creation error: %s", err.message), {
                    type: "warning",
                });
            }
        }

        this.state.import_progress = 100;
        this.state.is_importing = false;
        this.state.import_stats = { created, skipped, errors, edges: edgesToCreate.length };
        this.notification.add(
            _t("Import complete: %s created, %s edges, %s skipped.", created, edgesToCreate.length, skipped),
            { type: "success" }
        );
    }

    finishImport() {
        this.props.onImportComplete();
    }

    resetImport() {
        this.state.file_data = null;
        this.state.file_name = "";
        this.state.columns = [];
        this.state.mapping = [];
        this.state.metadata_keys = [];
        this.state.preview_rows = [];
        this.state.all_rows = [];
        this.state.import_stats = null;
        this.state.import_progress = 0;
    }
}
