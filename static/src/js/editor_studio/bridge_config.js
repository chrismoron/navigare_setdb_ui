/** @odoo-module */
import { Component, useState, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";

export class SetDBBridgeConfig extends Component {
    static template = "setdb_ui.BridgeConfig";
    static props = {
        onSave: { type: Function },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            bridges: [],
            selected_bridge: null,
            is_loading: false,
            is_syncing: false,
        });

        onMounted(() => {
            this.loadBridges();
        });
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------

    async loadBridges() {
        this.state.is_loading = true;
        try {
            const bridges = await this.orm.searchRead(
                "setdb.data.bridge",
                [["active", "=", true]],
                [
                    "id", "name", "source_model_id", "sync_mode",
                    "last_sync", "last_sync_count", "interval_number",
                    "interval_type", "domain_filter", "active",
                ],
                { order: "name asc" }
            );
            this.state.bridges = bridges;
        } catch (err) {
            this.notification.add(_t("Failed to load bridges."), { type: "danger" });
        } finally {
            this.state.is_loading = false;
        }
    }

    // ------------------------------------------------------------------
    // Selection & editing
    // ------------------------------------------------------------------

    selectBridge(bridge) {
        this.state.selected_bridge = { ...bridge };
    }

    deselectBridge() {
        this.state.selected_bridge = null;
    }

    onNameInput(ev) {
        if (this.state.selected_bridge) {
            this.state.selected_bridge.name = ev.target.value;
        }
    }

    onSyncModeChange(ev) {
        if (this.state.selected_bridge) {
            this.state.selected_bridge.sync_mode = ev.target.value;
        }
    }

    onIntervalNumberInput(ev) {
        if (this.state.selected_bridge) {
            this.state.selected_bridge.interval_number = parseInt(ev.target.value) || 1;
        }
    }

    onIntervalTypeChange(ev) {
        if (this.state.selected_bridge) {
            this.state.selected_bridge.interval_type = ev.target.value;
        }
    }

    onDomainFilterInput(ev) {
        if (this.state.selected_bridge) {
            this.state.selected_bridge.domain_filter = ev.target.value;
        }
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------

    async saveBridge() {
        const bridge = this.state.selected_bridge;
        if (!bridge) return;

        try {
            await this.orm.write("setdb.data.bridge", [bridge.id], {
                name: bridge.name,
                sync_mode: bridge.sync_mode,
                interval_number: bridge.interval_number,
                interval_type: bridge.interval_type,
                domain_filter: bridge.domain_filter,
            });
            this.notification.add(_t("Bridge saved."), { type: "success" });
            await this.loadBridges();
            this.state.selected_bridge = null;
            this.props.onSave();
        } catch (err) {
            this.notification.add(_t("Save failed: %s", err.message), { type: "danger" });
        }
    }

    async syncBridge(bridgeId) {
        this.state.is_syncing = true;
        try {
            const result = await rpc("/setdb_ui/bridge/sync", {
                bridge_id: bridgeId,
            });
            if (result.error) {
                this.notification.add(result.error, { type: "danger" });
            } else {
                this.notification.add(
                    _t("Sync complete: %s created, %s updated, %s skipped.",
                        result.created || 0, result.updated || 0, result.skipped || 0),
                    { type: "success" }
                );
                await this.loadBridges();
            }
        } catch (err) {
            this.notification.add(_t("Sync failed: %s", err.message), { type: "danger" });
        } finally {
            this.state.is_syncing = false;
        }
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    getSyncModeLabel(mode) {
        switch (mode) {
            case "manual": return _t("Manual");
            case "on_change": return _t("On Change");
            case "scheduled": return _t("Scheduled");
            default: return mode;
        }
    }

    getSyncStatusClass(bridge) {
        if (!bridge.last_sync) return "setdb-badge setdb-badge-warning";
        // If last sync was more than 24h ago, show warning
        const lastSync = new Date(bridge.last_sync);
        const hoursAgo = (Date.now() - lastSync.getTime()) / (1000 * 60 * 60);
        if (hoursAgo > 24) return "setdb-badge setdb-badge-warning";
        return "setdb-badge setdb-badge-success";
    }

    formatDate(dateStr) {
        if (!dateStr) return _t("Never");
        const d = new Date(dateStr);
        return d.toLocaleString();
    }
}
