import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBAISession(models.Model):
    _name = 'setdb.ai.session'
    _description = 'SetDB AI Assistant Session'
    _order = 'created_at desc'

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.uid, ondelete='cascade')
    message_ids = fields.One2many('setdb.ai.message', 'session_id', string='Messages')
    context_json = fields.Text(string='Session Context')
    created_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    name = fields.Char(compute='_compute_name', store=True)

    @api.depends('created_at')
    def _compute_name(self):
        for record in self:
            if record.created_at:
                record.name = 'AI Session %s' % fields.Datetime.to_string(record.created_at)
            else:
                record.name = 'AI Session (new)'

    def send_message(self, content, context=None):
        """Send a user message and get an AI assistant response.

        1. Create user message record
        2. Build system prompt with DAG context
        3. Call Claude API via ai_engine
        4. Create assistant message record
        5. Return assistant message
        """
        self.ensure_one()
        Message = self.env['setdb.ai.message']

        # Create user message
        Message.create({
            'session_id': self.id,
            'role': 'user',
            'content': content,
            'created_at': fields.Datetime.now(),
        })

        # Build message history for API call
        ai_engine = self.env['setdb.ai.engine']
        system_prompt = ai_engine.build_system_prompt()

        messages = []
        for msg in self.message_ids.sorted('created_at'):
            messages.append({
                'role': msg.role,
                'content': msg.content,
            })

        # Call AI engine
        try:
            response_text = ai_engine.chat(messages, system_prompt)
        except Exception as e:
            _logger.exception('AI engine call failed')
            response_text = 'I encountered an error processing your request: %s' % str(e)

        # Parse suggested query/action from response
        suggested_query = None
        suggested_action_json = None
        try:
            # Look for SetQL code blocks in the response
            import re
            setql_match = re.search(r'```(?:setql)?\s*\n(.+?)\n```', response_text, re.DOTALL)
            if setql_match:
                suggested_query = setql_match.group(1).strip()

            # Look for JSON action blocks
            action_match = re.search(r'```json\s*\n(\{.+?\})\n```', response_text, re.DOTALL)
            if action_match:
                suggested_action_json = action_match.group(1).strip()
        except Exception:
            pass

        # Create assistant message
        assistant_msg = Message.create({
            'session_id': self.id,
            'role': 'assistant',
            'content': response_text,
            'suggested_query': suggested_query,
            'suggested_action_json': suggested_action_json,
            'created_at': fields.Datetime.now(),
        })

        return assistant_msg


class SetDBAIMessage(models.Model):
    _name = 'setdb.ai.message'
    _description = 'SetDB AI Message'
    _order = 'created_at'

    session_id = fields.Many2one('setdb.ai.session', required=True, ondelete='cascade')
    role = fields.Selection([
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ], required=True)
    content = fields.Text(required=True)
    suggested_query = fields.Text(string='Suggested SetQL Query')
    suggested_action_json = fields.Text(string='Suggested Action (JSON)')
    created_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
