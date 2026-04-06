# setdb.saved_query — Saved, parameterized SetQL queries
from odoo import api, fields, models
from odoo.exceptions import UserError
import json

class SetDBSavedQuery(models.Model):
    _name = 'setdb.saved.query'
    _description = 'SetDB Saved Query'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    query_text = fields.Text(required=True)
    description = fields.Text()
    parameters_json = fields.Text(
        string='Parameters Schema',
        help='JSON array: [{"name": "account", "type": "element", "label": "Account", "default": "plan_kont"}]'
    )
    author_id = fields.Many2one('res.users', default=lambda self: self.env.uid, readonly=True)
    is_shared = fields.Boolean(default=False)
    shared_group_ids = fields.Many2many('res.groups', string='Shared With Groups')
    tags = fields.Char(help='Comma-separated tags')
    last_executed = fields.Datetime(readonly=True)
    execution_count = fields.Integer(default=0, readonly=True)
    avg_execution_time_ms = fields.Float(default=0, readonly=True)
    active = fields.Boolean(default=True)
    schedule_ids = fields.One2many('setdb.query.schedule', 'saved_query_id', string='Schedules')
    history_ids = fields.One2many('setdb.query.history', 'saved_query_id', string='History')

    _name_unique = models.Constraint('UNIQUE(name)', 'Query name must be unique.')

    def execute_query(self, parameters=None):
        """Execute the saved query with optional parameter substitution."""
        self.ensure_one()
        import time
        query_text = self.query_text
        if parameters and self.parameters_json:
            schema = json.loads(self.parameters_json)
            for param in schema:
                placeholder = '${' + param['name'] + '}'
                value = parameters.get(param['name'], param.get('default', ''))
                query_text = query_text.replace(placeholder, str(value))

        t0 = time.monotonic()
        try:
            executor = self.env['setdb.query.executor']
            result = executor.execute(query_text)
            elapsed = (time.monotonic() - t0) * 1000
            result_count = len(result) if hasattr(result, '__len__') else 0

            # Log history
            self.env['setdb.query.history'].create({
                'query_text': query_text,
                'saved_query_id': self.id,
                'user_id': self.env.uid,
                'execution_time_ms': elapsed,
                'result_count': result_count,
                'status': 'success',
                'parameters_json': json.dumps(parameters) if parameters else False,
            })

            # Update stats
            total_time = self.avg_execution_time_ms * self.execution_count + elapsed
            new_count = self.execution_count + 1
            self.write({
                'last_executed': fields.Datetime.now(),
                'execution_count': new_count,
                'avg_execution_time_ms': total_time / new_count,
            })
            return result
        except Exception as e:
            elapsed = (time.monotonic() - t0) * 1000
            self.env['setdb.query.history'].create({
                'query_text': query_text,
                'saved_query_id': self.id,
                'user_id': self.env.uid,
                'execution_time_ms': elapsed,
                'status': 'error',
                'error_message': str(e),
            })
            raise

    def action_execute(self):
        """Button action to execute query and show results."""
        self.ensure_one()
        result = self.execute_query()
        # Return action showing result elements
        if hasattr(result, 'ids') and result.ids:
            return {
                'type': 'ir.actions.act_window',
                'name': f'Results: {self.name}',
                'res_model': 'setdb.element',
                'view_mode': 'list,form',
                'domain': [('id', 'in', result.ids)],
                'target': 'current',
            }
        return {'type': 'ir.actions.act_window_close'}

    def action_open_schedule(self):
        """Open schedule creation form for this query."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Schedule: {self.name}',
            'res_model': 'setdb.query.schedule',
            'view_mode': 'form',
            'context': {'default_saved_query_id': self.id, 'default_name': f'Schedule: {self.name}'},
            'target': 'new',
        }

    def get_parameters_schema(self):
        """Return parsed parameter schema for the UI."""
        self.ensure_one()
        if self.parameters_json:
            return json.loads(self.parameters_json)
        return []
