import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SetDBDataBridge(models.Model):
    _name = 'setdb.data.bridge'
    _description = 'SetDB Data Bridge'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    source_model_id = fields.Many2one('ir.model', required=True, ondelete='cascade')
    target_hierarchy_id = fields.Many2one('setdb.hierarchy', ondelete='set null')
    mapping_ids = fields.One2many('setdb.data.bridge.mapping', 'bridge_id', string='Field Mappings')
    dimension_ids = fields.One2many('setdb.data.bridge.dimension', 'bridge_id', string='Dimensions')
    sync_mode = fields.Selection([
        ('manual', 'Manual'),
        ('on_change', 'On Change'),
        ('scheduled', 'Scheduled'),
    ], default='manual', required=True)
    domain_filter = fields.Text(default='[]', help='Odoo domain filter for source records')
    cron_id = fields.Many2one('ir.cron', readonly=True, ondelete='set null')
    interval_number = fields.Integer(default=1)
    interval_type = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
    ], default='days')
    last_sync = fields.Datetime(readonly=True)
    last_sync_count = fields.Integer(readonly=True)
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint('UNIQUE(name)', 'Bridge name must be unique.')

    def action_sync(self):
        """Manually trigger a sync through the bridge engine."""
        self.ensure_one()
        engine = self.env['setdb.bridge.engine']
        stats = engine.sync_bridge(self)
        self.write({
            'last_sync': fields.Datetime.now(),
            'last_sync_count': stats.get('created', 0) + stats.get('updated', 0),
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Complete',
                'message': 'Created: %d, Updated: %d, Skipped: %d' % (
                    stats.get('created', 0),
                    stats.get('updated', 0),
                    stats.get('skipped', 0),
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_preview(self):
        """Preview sync results without applying changes."""
        self.ensure_one()
        engine = self.env['setdb.bridge.engine']
        preview = engine.preview_bridge(self)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sync Preview',
                'message': 'Would create: %d, update: %d, skip: %d' % (
                    preview.get('created', 0),
                    preview.get('updated', 0),
                    preview.get('skipped', 0),
                ),
                'type': 'info',
                'sticky': False,
            },
        }

    def _create_scheduled_cron(self):
        """Create or update the ir.cron for scheduled sync."""
        self.ensure_one()
        if self.cron_id:
            self.cron_id.write({
                'interval_number': self.interval_number,
                'interval_type': self.interval_type,
                'active': self.active and self.sync_mode == 'scheduled',
            })
        else:
            cron = self.env['ir.cron'].create({
                'name': 'SetDB Bridge Sync: %s' % self.name,
                'model_id': self.env['ir.model']._get_id(self._name),
                'state': 'code',
                'code': 'model._cron_sync_bridge(%d)' % self.id,
                'interval_number': self.interval_number,
                'interval_type': self.interval_type,
                'active': self.active and self.sync_mode == 'scheduled',
            })
            self.cron_id = cron

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.sync_mode == 'scheduled':
                record._create_scheduled_cron()
        return records

    def write(self, vals):
        res = super().write(vals)
        if any(f in vals for f in ('sync_mode', 'interval_number', 'interval_type', 'active')):
            for record in self:
                if record.sync_mode == 'scheduled':
                    record._create_scheduled_cron()
                elif record.cron_id:
                    record.cron_id.write({'active': False})
        return res

    def unlink(self):
        crons = self.mapped('cron_id')
        res = super().unlink()
        crons.unlink()
        return res

    @api.model
    def _cron_sync_bridge(self, bridge_id):
        """Called by ir.cron to execute a scheduled sync."""
        bridge = self.browse(bridge_id)
        if not bridge.exists() or not bridge.active:
            return
        try:
            bridge.action_sync()
        except Exception:
            _logger.exception('SetDB bridge sync failed for bridge %s (id=%d)', bridge.name, bridge.id)


class SetDBDataBridgeMapping(models.Model):
    _name = 'setdb.data.bridge.mapping'
    _description = 'SetDB Data Bridge Field Mapping'
    _order = 'sequence, id'

    bridge_id = fields.Many2one('setdb.data.bridge', required=True, ondelete='cascade')
    source_field_id = fields.Many2one('ir.model.fields', required=True, ondelete='cascade')
    mapping_type = fields.Selection([
        ('name', 'Element Name'),
        ('metadata', 'Metadata Value'),
        ('parent', 'Parent Relationship'),
        ('element_type', 'Element Type'),
        ('period', 'Period'),
    ], required=True, default='metadata')
    metadata_key = fields.Char(help='Key name when mapping_type is metadata')
    sequence = fields.Integer(default=10)


class SetDBDataBridgeDimension(models.Model):
    _name = 'setdb.data.bridge.dimension'
    _description = 'SetDB Data Bridge Dimension'
    _order = 'id'

    bridge_id = fields.Many2one('setdb.data.bridge', required=True, ondelete='cascade')
    odoo_field_id = fields.Many2one(
        'ir.model.fields', required=True, ondelete='cascade',
        help='e.g., analytic_account_id, department_id, date',
    )
    target_hierarchy_id = fields.Many2one('setdb.hierarchy', ondelete='set null')
    period_config_id = fields.Many2one(
        'setdb.period.config', ondelete='set null',
        help='For date fields, link to period config',
    )
    auto_create_hierarchy = fields.Boolean(default=True)
