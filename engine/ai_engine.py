import json
import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

CLAUDE_API_URL = 'https://api.anthropic.com/v1/messages'


class SetDBAIEngine(models.AbstractModel):
    _name = 'setdb.ai.engine'
    _description = 'SetDB AI Engine (Claude API)'

    @api.model
    def chat(self, messages, system_prompt):
        """Call Claude API with conversation messages and system prompt.

        Args:
            messages: list of dicts with 'role' and 'content' keys
            system_prompt: string with system context

        Returns:
            Assistant response content text.
        """
        ICP = self.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('setdb_ui.ai_api_key', '')
        model = ICP.get_param('setdb_ui.ai_model', 'claude-sonnet-4-20250514')
        max_tokens = int(ICP.get_param('setdb_ui.ai_max_tokens', 4096))

        if not api_key:
            return (
                'AI assistant is not configured. '
                'Please set the API key in Settings > SetDB > AI Configuration.'
            )

        headers = {
            'Content-Type': 'application/json',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
        }

        payload = {
            'model': model,
            'max_tokens': max_tokens,
            'system': system_prompt,
            'messages': messages,
        }

        try:
            response = requests.post(
                CLAUDE_API_URL,
                headers=headers,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()

            # Extract text from response content blocks
            content_blocks = data.get('content', [])
            text_parts = []
            for block in content_blocks:
                if block.get('type') == 'text':
                    text_parts.append(block['text'])
            return '\n'.join(text_parts) if text_parts else 'No response generated.'

        except requests.exceptions.Timeout:
            _logger.warning('Claude API request timed out')
            return 'The AI request timed out. Please try again with a simpler query.'
        except requests.exceptions.HTTPError as e:
            _logger.error('Claude API HTTP error: %s', e)
            return 'AI service error: %s' % str(e)
        except Exception as e:
            _logger.exception('Claude API call failed')
            return 'AI service unavailable: %s' % str(e)

    @api.model
    def build_system_prompt(self):
        """Generate a system prompt with context about the current DAG state.

        Includes:
        - Element and edge counts
        - Hierarchy names and root elements
        - Available SetQL operations
        - Recent query history
        - Active sigma-algebras and filters
        """
        Element = self.env['setdb.element']
        Edge = self.env['setdb.edge']
        Hierarchy = self.env['setdb.hierarchy']

        # Counts
        element_count = Element.search_count([])
        edge_count = Edge.search_count([])

        # Hierarchies
        hierarchies = Hierarchy.search([], limit=50)
        hierarchy_info = []
        for h in hierarchies:
            root_name = h.root_id.name if h.root_id else '(no root)'
            hierarchy_info.append('- %s (type: %s, root: %s)' % (h.name, h.hierarchy_type, root_name))

        # Available SetQL operations
        setql_ops = [
            'FLATTEN(set) — recursively collect all primitives',
            'MEMBERS(set) — direct children of a set',
            'UNION(A, B) — set union',
            'INTERSECT(A, B) — set intersection',
            'DIFFERENCE(A, B) — set difference',
            'COMPLEMENT(A) — complement within omega',
            'SYMMETRIC_DIFF(A, B) — symmetric difference',
            'ANCESTORS(element) — all ancestor sets',
            'REACHABLE(start VIA path) — reachable elements',
            'FIND(conditions) — search elements by criteria',
        ]

        # Recent query history
        History = self.env.get('setdb.query.history')
        recent_queries = []
        if History is not None:
            history_records = History.search([], order='executed_at desc', limit=10)
            for h in history_records:
                recent_queries.append('- %s (status: %s)' % (
                    (h.query_text or '')[:80], h.status,
                ))

        # Active sigma-algebras
        SigmaAlgebra = self.env.get('setdb.sigma.algebra')
        sigma_info = []
        if SigmaAlgebra is not None:
            algebras = SigmaAlgebra.search([('active', '=', True)], limit=20)
            for sa in algebras:
                sigma_info.append('- %s' % sa.name)

        # Active filters
        Filter = self.env.get('setdb.filter')
        filter_info = []
        if Filter is not None:
            filters = Filter.search([('active', '=', True)], limit=20)
            for f in filters:
                filter_info.append('- %s (type: %s, policy: %s)' % (f.name, f.filter_type, f.policy))

        prompt_parts = [
            'You are an AI assistant for SetDB, a set-theoretic database built on Odoo.',
            'You help users query and manage hierarchical data using SetQL (Set Query Language).',
            '',
            '## Current DAG State',
            'Elements: %d' % element_count,
            'Edges: %d' % edge_count,
            '',
        ]

        if hierarchy_info:
            prompt_parts.append('## Hierarchies')
            prompt_parts.extend(hierarchy_info)
            prompt_parts.append('')

        prompt_parts.append('## Available SetQL Operations')
        prompt_parts.extend(['- %s' % op for op in setql_ops])
        prompt_parts.append('')

        if recent_queries:
            prompt_parts.append('## Recent Queries')
            prompt_parts.extend(recent_queries)
            prompt_parts.append('')

        if sigma_info:
            prompt_parts.append('## Active Sigma-Algebras')
            prompt_parts.extend(sigma_info)
            prompt_parts.append('')

        if filter_info:
            prompt_parts.append('## Active Filters')
            prompt_parts.extend(filter_info)
            prompt_parts.append('')

        prompt_parts.extend([
            '## Response Guidelines',
            '- When suggesting queries, wrap them in ```setql code blocks.',
            '- When suggesting actions, wrap them in ```json code blocks.',
            '- Explain your reasoning before providing queries.',
            '- Reference specific hierarchies and elements by name when possible.',
        ])

        return '\n'.join(prompt_parts)
