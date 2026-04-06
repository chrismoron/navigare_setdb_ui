/** @odoo-module */
import { Component, useState, useRef, onMounted } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";
import { SetDBSuggestion } from "./suggestion";

export class SetDBAssistant extends Component {
    static template = "setdb_ui.Assistant";
    static components = { SetDBSuggestion };
    static props = {
        onApplyQuery: { type: Function },
    };

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");

        this.state = useState({
            messages: [],
            input_text: "",
            is_typing: false,
            session_id: null,
        });

        this.messagesRef = useRef("messages");
    }

    // ------------------------------------------------------------------
    // Chat
    // ------------------------------------------------------------------

    async sendMessage() {
        const text = this.state.input_text.trim();
        if (!text) return;

        // Add user message locally
        this.state.messages.push({
            role: "user",
            content: text,
            suggestions: [],
        });
        this.state.input_text = "";
        this.state.is_typing = true;
        this._scrollToBottom();

        try {
            const result = await this.rpc("/setdb_ui/ai/chat", {
                message: text,
                session_id: this.state.session_id,
                context: {},
            });

            if (result.error) {
                this.state.messages.push({
                    role: "assistant",
                    content: _t("Error: %s", result.error),
                    suggestions: [],
                });
            } else {
                this.state.session_id = result.session_id;
                this.state.messages.push({
                    role: "assistant",
                    content: result.response || "",
                    suggestions: result.suggestions || [],
                });
            }
        } catch (err) {
            this.state.messages.push({
                role: "assistant",
                content: _t("Connection error. Please try again."),
                suggestions: [],
            });
        } finally {
            this.state.is_typing = false;
            this._scrollToBottom();
        }
    }

    onInputChange(ev) {
        this.state.input_text = ev.target.value;
    }

    onInputKeydown(ev) {
        // Enter sends, Shift+Enter creates new line
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }

    onApplySuggestion(query, actionJson) {
        this.props.onApplyQuery(query, actionJson);
    }

    // ------------------------------------------------------------------
    // Quick prompts
    // ------------------------------------------------------------------

    askQuickPrompt(prompt) {
        this.state.input_text = prompt;
        this.sendMessage();
    }

    // ------------------------------------------------------------------
    // Session
    // ------------------------------------------------------------------

    newSession() {
        this.state.messages = [];
        this.state.session_id = null;
        this.state.input_text = "";
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    _scrollToBottom() {
        // Use requestAnimationFrame to wait for DOM update
        window.requestAnimationFrame(() => {
            const el = this.messagesRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    get hasMessages() {
        return this.state.messages.length > 0;
    }

    get quickPrompts() {
        return [
            _t("Show all top-level sets"),
            _t("Find elements with type 'primitive'"),
            _t("What hierarchies exist?"),
            _t("Write a query to flatten a set"),
        ];
    }

    formatContent(content) {
        if (!content) return "";
        // Basic markdown-like formatting: **bold**, `code`, ```blocks```
        let html = content
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Code blocks
        html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre class="setdb-ai-code-block"><code>${code}</code></pre>`;
        });
        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code class="setdb-ai-inline-code">$1</code>');
        // Bold
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        // Newlines
        html = html.replace(/\n/g, "<br/>");
        return html;
    }
}
