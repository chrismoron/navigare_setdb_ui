import csv
import io
import json
import logging
import re

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBMailQuery(models.Model):
    _name = 'setdb.mail.query'
    _description = 'SetDB Mail Query Integration'
    _inherit = ['mail.thread']
    _mail_post_access = 'read'
    _order = 'name'

    name = fields.Char(required=True, default='SetDB Mail Query')
    alias_id = fields.Many2one('mail.alias', string='Email Alias', ondelete='set null')
    allowed_user_ids = fields.Many2many('res.users', string='Allowed Users')
    response_format = fields.Selection([
        ('html_table', 'HTML Table'),
        ('csv_attachment', 'CSV Attachment'),
        ('both', 'Both'),
    ], default='html_table', required=True)
    max_results = fields.Integer(default=1000)
    active = fields.Boolean(default=True)

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """Handle incoming email: extract query, execute, and reply with results."""
        custom_values = custom_values or {}
        record = super().message_new(msg_dict, custom_values=custom_values)
        record._process_incoming_email(msg_dict)
        return record

    def message_update(self, msg_dict, update_vals=None):
        """Handle follow-up emails on existing thread."""
        res = super().message_update(msg_dict, update_vals=update_vals)
        self._process_incoming_email(msg_dict)
        return res

    def _process_incoming_email(self, msg_dict):
        """Extract query from email, execute, and reply."""
        self.ensure_one()

        # Check sender authorization
        author_id = msg_dict.get('author_id')
        if self.allowed_user_ids:
            allowed_partner_ids = self.allowed_user_ids.mapped('partner_id').ids
            if author_id and author_id not in allowed_partner_ids:
                self.message_post(
                    body='<p>Access denied: your account is not authorized to execute queries.</p>',
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
                return

        # Extract query text
        body = msg_dict.get('body', '')
        query_text = self._extract_query_text(body)
        subject = msg_dict.get('subject', '').strip()

        if not query_text and not subject:
            self.message_post(
                body='<p>No query found in the email body or subject.</p>',
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
            return

        # Check if subject matches a saved query name
        SavedQuery = self.env['setdb.saved.query']
        saved_query = SavedQuery.search([('name', '=', subject)], limit=1) if subject else SavedQuery

        try:
            if saved_query:
                result = saved_query.execute_query()
            else:
                executor = self.env['setdb.query.executor']
                result = executor.execute(query_text or subject)

            self._reply_with_results(result, query_text or subject)
        except Exception as e:
            _logger.exception('SetDB mail query execution failed')
            self.message_post(
                body='<p>Query execution error: %s</p>' % str(e),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )

    def _extract_query_text(self, body):
        """Extract plain text query from email body, stripping HTML."""
        if not body:
            return ''
        # Strip HTML tags
        clean = re.sub(r'<[^>]+>', ' ', body)
        # Collapse whitespace
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def _reply_with_results(self, result, query_text):
        """Format and post results as a reply."""
        self.ensure_one()

        elements = result if hasattr(result, 'ids') else self.env['setdb.element'].browse()
        if self.max_results and len(elements) > self.max_results:
            elements = elements[:self.max_results]

        attachments = []

        # Build HTML table
        html_body = '<h3>SetDB Query Results</h3>'
        html_body += '<p><em>Query: %s</em></p>' % query_text

        if not elements:
            html_body += '<p>No results found.</p>'
        else:
            html_body += '<p>%d element(s) returned.</p>' % len(elements)
            if self.response_format in ('html_table', 'both'):
                html_body += self._format_html_table(elements)

        # Build CSV attachment
        if self.response_format in ('csv_attachment', 'both') and elements:
            csv_data = self._format_csv(elements)
            attachments.append(('query_results.csv', csv_data.encode('utf-8')))

        kwargs = {
            'body': html_body,
            'message_type': 'comment',
            'subtype_xmlid': 'mail.mt_comment',
        }
        if attachments:
            Attachment = self.env['ir.attachment']
            attachment_ids = []
            for fname, fcontent in attachments:
                att = Attachment.create({
                    'name': fname,
                    'datas': self.env['base'].with_context()._encode_base64(fcontent)
                    if hasattr(self.env['base'], '_encode_base64')
                    else __import__('base64').b64encode(fcontent),
                    'res_model': self._name,
                    'res_id': self.id,
                })
                attachment_ids.append(att.id)
            kwargs['attachment_ids'] = [fields.Command.set(attachment_ids)]

        self.message_post(**kwargs)

    def _format_html_table(self, elements):
        """Format elements as an HTML table."""
        html = '<table border="1" cellpadding="4" cellspacing="0">'
        html += '<tr><th>Name</th><th>Type</th><th>GUID</th></tr>'
        for el in elements[:500]:
            html += '<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                el.name, el.element_type, el.guid,
            )
        html += '</table>'
        if len(elements) > 500:
            html += '<p>... and %d more elements (truncated)</p>' % (len(elements) - 500)
        return html

    def _format_csv(self, elements):
        """Format elements as CSV string."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Name', 'Type', 'GUID', 'Metadata'])
        for el in elements:
            writer.writerow([el.name, el.element_type, el.guid, el.metadata_json or ''])
        return output.getvalue()
