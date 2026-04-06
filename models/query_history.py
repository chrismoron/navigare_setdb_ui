# setdb.query.history — Query execution history
from odoo import api, fields, models

class SetDBQueryHistory(models.Model):
    _name = 'setdb.query.history'
    _description = 'SetDB Query Execution History'
    _order = 'executed_at desc'

    query_text = fields.Text(required=True)
    saved_query_id = fields.Many2one('setdb.saved.query', ondelete='set null', index=True)
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.uid, index=True)
    executed_at = fields.Datetime(default=fields.Datetime.now, index=True)
    execution_time_ms = fields.Float(string='Execution Time (ms)')
    result_count = fields.Integer(string='Result Count')
    execution_plan = fields.Text()
    status = fields.Selection([
        ('success', 'Success'),
        ('error', 'Error'),
    ], required=True, default='success')
    error_message = fields.Text()
    parameters_json = fields.Text(string='Parameters Used')

    def action_rerun(self):
        """Re-execute this query."""
        self.ensure_one()
        executor = self.env['setdb.query.executor']
        result = executor.execute(self.query_text)
        if hasattr(result, 'ids') and result.ids:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Re-run Results',
                'res_model': 'setdb.element',
                'view_mode': 'list,form',
                'domain': [('id', 'in', result.ids)],
            }
