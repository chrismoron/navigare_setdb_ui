/** @odoo-module */
import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";

const SETQL_KEYWORDS = [
    "UNION", "INTERSECT", "DIFFERENCE", "SYMMETRIC_DIFF", "COMPLEMENT",
    "FLATTEN", "MEMBERS", "ANCESTORS", "REACHABLE", "FIND",
    "WHERE", "AND", "OR", "NOT", "IN", "LIKE", "BETWEEN",
    "ORDER BY", "ASC", "DESC", "LIMIT", "OFFSET",
    "AS", "WITH", "LET", "EXPLAIN",
];

const KEYWORD_REGEX = new RegExp(
    "\\b(" + SETQL_KEYWORDS.join("|") + ")\\b",
    "gi"
);
const STRING_REGEX = /(["'])(?:(?!\1|\\).|\\.)*\1/g;
const COMMENT_REGEX = /--[^\n]*/g;
const NUMBER_REGEX = /\b\d+(?:\.\d+)?\b/g;
const ELEMENT_REF_REGEX = /\$\{[^}]+\}/g;

export class SetDBQueryEditor extends Component {
    static template = "setdb_ui.QueryEditor";
    static props = {
        value: { type: String },
        onChange: { type: Function },
        onExecute: { type: Function },
    };

    setup() {
        this.state = useState({
            showAutocomplete: false,
            autocompleteItems: [],
            autocompleteIndex: 0,
            autocompleteTop: 0,
            autocompleteLeft: 0,
        });
        this.textareaRef = useRef("textarea");
        this.highlightRef = useRef("highlight");

        onMounted(() => {
            this._syncScroll();
        });
    }

    get highlightedHtml() {
        let text = this.props.value || "";
        // Escape HTML
        text = text
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Apply syntax highlighting in priority order
        // 1) Comments
        text = text.replace(COMMENT_REGEX, (m) => `<span class="setdb-hl-comment">${m}</span>`);
        // 2) Strings
        text = text.replace(STRING_REGEX, (m) => `<span class="setdb-hl-string">${m}</span>`);
        // 3) Element refs ${...}
        text = text.replace(ELEMENT_REF_REGEX, (m) => `<span class="setdb-hl-ref">${m}</span>`);
        // 4) Numbers
        text = text.replace(NUMBER_REGEX, (m) => `<span class="setdb-hl-number">${m}</span>`);
        // 5) Keywords
        text = text.replace(KEYWORD_REGEX, (m) => `<span class="setdb-hl-keyword">${m}</span>`);

        // Ensure trailing newline so highlight layer matches textarea height
        if (text.endsWith("\n")) {
            text += " ";
        }
        return text;
    }

    onInput(ev) {
        this.props.onChange(ev.target.value);
        this._closeAutocomplete();
    }

    onKeydown(ev) {
        // Ctrl+Enter -> execute
        if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
            ev.preventDefault();
            this.props.onExecute();
            return;
        }
        // Ctrl+Space -> autocomplete
        if (ev.key === " " && ev.ctrlKey) {
            ev.preventDefault();
            this._openAutocomplete();
            return;
        }
        // Tab inserts spaces
        if (ev.key === "Tab") {
            ev.preventDefault();
            const ta = ev.target;
            const start = ta.selectionStart;
            const end = ta.selectionEnd;
            const val = ta.value;
            ta.value = val.substring(0, start) + "    " + val.substring(end);
            ta.selectionStart = ta.selectionEnd = start + 4;
            this.props.onChange(ta.value);
            return;
        }
        // Autocomplete navigation
        if (this.state.showAutocomplete) {
            if (ev.key === "ArrowDown") {
                ev.preventDefault();
                this.state.autocompleteIndex = Math.min(
                    this.state.autocompleteIndex + 1,
                    this.state.autocompleteItems.length - 1
                );
            } else if (ev.key === "ArrowUp") {
                ev.preventDefault();
                this.state.autocompleteIndex = Math.max(this.state.autocompleteIndex - 1, 0);
            } else if (ev.key === "Enter" || ev.key === "Tab") {
                ev.preventDefault();
                this._insertAutocomplete(this.state.autocompleteItems[this.state.autocompleteIndex]);
            } else if (ev.key === "Escape") {
                this._closeAutocomplete();
            }
        }
    }

    onScroll() {
        this._syncScroll();
    }

    _syncScroll() {
        const ta = this.textareaRef.el;
        const hl = this.highlightRef.el;
        if (ta && hl) {
            hl.scrollTop = ta.scrollTop;
            hl.scrollLeft = ta.scrollLeft;
        }
    }

    _openAutocomplete() {
        const ta = this.textareaRef.el;
        if (!ta) return;
        const pos = ta.selectionStart;
        const textBefore = ta.value.substring(0, pos);
        // Get partial word being typed
        const match = textBefore.match(/(\w+)$/);
        const partial = match ? match[1].toUpperCase() : "";

        const items = SETQL_KEYWORDS.filter(
            (kw) => !partial || kw.startsWith(partial)
        );
        if (items.length === 0) return;

        // Compute approximate position
        const lines = textBefore.split("\n");
        const lineIndex = lines.length - 1;
        const colIndex = lines[lineIndex].length;
        const lineHeight = 20;
        const charWidth = 8.4;

        this.state.autocompleteItems = items;
        this.state.autocompleteIndex = 0;
        this.state.autocompleteTop = (lineIndex + 1) * lineHeight - ta.scrollTop;
        this.state.autocompleteLeft = colIndex * charWidth - ta.scrollLeft;
        this.state.showAutocomplete = true;
    }

    _closeAutocomplete() {
        this.state.showAutocomplete = false;
        this.state.autocompleteItems = [];
    }

    _insertAutocomplete(keyword) {
        if (!keyword) return;
        const ta = this.textareaRef.el;
        const pos = ta.selectionStart;
        const val = ta.value;
        const before = val.substring(0, pos);
        const after = val.substring(pos);
        // Replace partial word
        const match = before.match(/(\w+)$/);
        const partial = match ? match[1] : "";
        const newBefore = before.substring(0, before.length - partial.length) + keyword + " ";
        ta.value = newBefore + after;
        ta.selectionStart = ta.selectionEnd = newBefore.length;
        this.props.onChange(ta.value);
        this._closeAutocomplete();
        ta.focus();
    }

    selectAutocompleteItem(index) {
        this._insertAutocomplete(this.state.autocompleteItems[index]);
    }
}
