import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBUIProfile(models.Model):
    _name = 'setdb.ui.profile'
    _description = 'SetDB UI User Profile'
    _order = 'name'

    name = fields.Char(required=True)
    user_id = fields.Many2one('res.users', ondelete='cascade')
    is_default = fields.Boolean(default=False)
    is_shared = fields.Boolean(default=False)
    default_cube_id = fields.Many2one('setdb.cube', ondelete='set null', string='Default Cube')
    default_query_id = fields.Many2one('setdb.saved.query', ondelete='set null', string='Default Query')
    dashboard_layout_json = fields.Text(default='{}', string='Dashboard Layout')
    keyboard_shortcuts_json = fields.Text(default='{}', string='Keyboard Shortcuts')


class SetDBUITemplate(models.Model):
    _name = 'setdb.ui.template'
    _description = 'SetDB UI Template'
    _order = 'name'

    name = fields.Char(required=True)
    template_type = fields.Selection([
        ('query', 'Saved Query'),
        ('cube', 'Cube'),
        ('bridge', 'Data Bridge'),
    ], required=True)
    config_json = fields.Text(required=True, string='Configuration (JSON)')
    description = fields.Text()
    tags = fields.Char(help='Comma-separated tags')
    is_system = fields.Boolean(default=False)

    def action_apply(self):
        """Create a new saved_query, cube, or bridge from this template config."""
        self.ensure_one()
        try:
            config = json.loads(self.config_json)
        except (json.JSONDecodeError, TypeError) as e:
            raise UserError('Invalid template configuration JSON: %s' % str(e))

        if self.template_type == 'query':
            record = self.env['setdb.saved.query'].create({
                'name': config.get('name', '%s (from template)' % self.name),
                'query_text': config.get('query_text', ''),
                'description': config.get('description', self.description or ''),
                'parameters_json': json.dumps(config.get('parameters', [])),
            })
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'setdb.saved.query',
                'res_id': record.id,
                'view_mode': 'form',
                'target': 'current',
            }

        elif self.template_type == 'cube':
            record = self.env['setdb.cube'].create({
                'name': config.get('name', '%s (from template)' % self.name),
            })
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'setdb.cube',
                'res_id': record.id,
                'view_mode': 'form',
                'target': 'current',
            }

        elif self.template_type == 'bridge':
            bridge_vals = {
                'name': config.get('name', '%s (from template)' % self.name),
                'sync_mode': config.get('sync_mode', 'manual'),
                'domain_filter': config.get('domain_filter', '[]'),
            }
            # Resolve source model if provided
            if config.get('source_model'):
                model = self.env['ir.model'].search(
                    [('model', '=', config['source_model'])], limit=1,
                )
                if model:
                    bridge_vals['source_model_id'] = model.id
            record = self.env['setdb.data.bridge'].create(bridge_vals)
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'setdb.data.bridge',
                'res_id': record.id,
                'view_mode': 'form',
                'target': 'current',
            }

        raise UserError('Unknown template type: %s' % self.template_type)
