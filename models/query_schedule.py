# setdb.query.schedule — Scheduled query execution
from odoo import api, fields, models
from odoo.exceptions import UserError
import json

class SetDBQuerySchedule(models.Model):
    _name = 'setdb.query.schedule'
    _description = 'SetDB Scheduled Query'
    _order = 'name'

    name = fields.Char(required=True)
    saved_query_id = fields.Many2one('setdb.saved.query', required=True, ondelete='cascade')
    cron_id = fields.Many2one('ir.cron', readonly=True, ondelete='set null')
    interval_number = fields.Integer(default=1, required=True)
    interval_type = fields.Selection([
        ('minutes', 'Minutes'),
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
        ('months', 'Months'),
    ], default='days', required=True)
    active = fields.Boolean(default=True)
    notify_user_ids = fields.Many2many('res.users', string='Notify Users')
    last_run = fields.Datetime(readonly=True)
    last_result_text = fields.Text(readonly=True)
    parameters_json = fields.Text(string='Execution Parameters')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._create_cron()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('interval_number', 'interval_type', 'active', 'saved_query_id')):
            for record in self:
                record._update_cron()
        return res

    def unlink(self):
        crons = self.mapped('cron_id')
        res = super().unlink()
        crons.unlink()
        return res

    def _create_cron(self):
        """Create an ir.cron record for this schedule."""
        self.ensure_one()
        cron = self.env['ir.cron'].create({
            'name': f'SetDB Schedule: {self.name}',
            'model_id': self.env['ir.model']._get_id(self._name),
            'state': 'code',
            'code': f'model._cron_execute_schedule({self.id})',
            'interval_number': self.interval_number,
            'interval_type': self.interval_type,
            'active': self.active,
        })
        self.cron_id = cron

    def _update_cron(self):
        """Update the linked cron job."""
        self.ensure_one()
        if self.cron_id:
            self.cron_id.write({
                'interval_number': self.interval_number,
                'interval_type': self.interval_type,
                'active': self.active,
            })

    @api.model
    def _cron_execute_schedule(self, schedule_id):
        """Called by ir.cron to execute a scheduled query."""
        schedule = self.browse(schedule_id)
        if not schedule.exists() or not schedule.active:
            return

        params = json.loads(schedule.parameters_json) if schedule.parameters_json else None
        try:
            result = schedule.saved_query_id.execute_query(parameters=params)
            result_count = len(result) if hasattr(result, '__len__') else 0
            result_text = f'Success: {result_count} elements returned'
            schedule.write({
                'last_run': fields.Datetime.now(),
                'last_result_text': result_text,
            })
            # Notify users
            if schedule.notify_user_ids:
                schedule._notify_users(result_text, result)
        except Exception as e:
            schedule.write({
                'last_run': fields.Datetime.now(),
                'last_result_text': f'Error: {str(e)}',
            })

    def _notify_users(self, result_text, result):
        """Send email notification to configured users."""
        self.ensure_one()
        if not self.notify_user_ids:
            return
        # Build HTML result table
        body = f'<h3>SetDB Query: {self.saved_query_id.name}</h3>'
        body += f'<p>{result_text}</p>'
        if hasattr(result, 'ids') and result.ids:
            body += '<table border="1" cellpadding="4"><tr><th>Name</th><th>Type</th><th>GUID</th></tr>'
            for el in result[:100]:  # Limit to 100 rows
                body += f'<tr><td>{el.name}</td><td>{el.element_type}</td><td>{el.guid}</td></tr>'
            body += '</table>'
            if len(result) > 100:
                body += f'<p>... and {len(result) - 100} more elements</p>'

        partner_ids = self.notify_user_ids.mapped('partner_id').ids
        self.env['mail.mail'].create({
            'subject': f'SetDB Report: {self.saved_query_id.name}',
            'body_html': body,
            'recipient_ids': [fields.Command.set(partner_ids)],
            'auto_delete': True,
        }).send()
