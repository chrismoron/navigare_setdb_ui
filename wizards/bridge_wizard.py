import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class SetDBBridgeWizard(models.TransientModel):
    _name = 'setdb.bridge.wizard'
    _description = 'SetDB Data Bridge Setup Wizard'

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------
    step = fields.Selection([
        ('1_source', 'Source'),
        ('2_mappings', 'Mappings'),
        ('3_dimensions', 'Dimensions'),
        ('4_review', 'Review'),
    ], default='1_source', required=True)

    # ------------------------------------------------------------------
    # Step 1: Source
    # ------------------------------------------------------------------
    name = fields.Char(string='Bridge Name', required=True)
    source_model_id = fields.Many2one(
        'ir.model', string='Source Model',
        domain=[('transient', '=', False)],
        help='The Odoo model to bridge data from.',
    )
    domain_filter = fields.Text(
        string='Domain Filter', default='[]',
        help='Odoo domain expression to filter source records.',
    )
    sync_mode = fields.Selection([
        ('manual', 'Manual'),
        ('scheduled', 'Scheduled'),
    ], default='manual', required=True)
    interval_number = fields.Integer(string='Interval Number', default=1)
    interval_type = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days'),
        ('weeks', 'Weeks'),
    ], default='days')

    # ------------------------------------------------------------------
    # Step 2: Mappings
    # ------------------------------------------------------------------
    available_field_ids = fields.Many2many(
        'ir.model.fields', 'setdb_bridge_wiz_avail_field_rel',
        string='Available Fields',
        compute='_compute_available_fields',
    )
    name_field_id = fields.Many2one(
        'ir.model.fields', string='Name Field',
        help='Source field to use as the element name.',
    )
    metadata_field_ids = fields.Many2many(
        'ir.model.fields', 'setdb_bridge_wiz_meta_field_rel',
        string='Metadata Fields',
        help='Source fields to include in metadata_json.',
    )
    parent_field_id = fields.Many2one(
        'ir.model.fields', string='Parent Field',
        help='Many2one field for parent hierarchy relationship.',
    )

    # ------------------------------------------------------------------
    # Step 3: Dimensions
    # ------------------------------------------------------------------
    date_field_id = fields.Many2one(
        'ir.model.fields', string='Date Field',
        help='Date/datetime field for period dimension.',
    )
    period_config_id = fields.Many2one(
        'setdb.period.config', string='Period Configuration',
        help='Period config to use for date dimension mapping.',
    )
    dimension_field_ids = fields.Many2many(
        'ir.model.fields', 'setdb_bridge_wiz_dim_field_rel',
        string='Dimension Fields',
        help='Many2one fields to use as additional dimensions.',
    )

    # ------------------------------------------------------------------
    # Step 4: Review
    # ------------------------------------------------------------------
    preview_count = fields.Integer(
        string='Matching Records', readonly=True,
        compute='_compute_preview_count',
    )
    review_text = fields.Text(
        string='Configuration Summary', readonly=True,
        compute='_compute_review_text',
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------
    @api.depends('source_model_id')
    def _compute_available_fields(self):
        for wiz in self:
            if wiz.source_model_id:
                wiz.available_field_ids = self.env['ir.model.fields'].search([
                    ('model_id', '=', wiz.source_model_id.id),
                    ('ttype', 'not in', ['one2many', 'binary', 'reference']),
                    ('store', '=', True),
                ])
            else:
                wiz.available_field_ids = self.env['ir.model.fields']

    @api.depends('source_model_id', 'domain_filter')
    def _compute_preview_count(self):
        for wiz in self:
            if wiz.source_model_id:
                try:
                    domain = safe_eval(wiz.domain_filter or '[]')
                    model = self.env[wiz.source_model_id.model]
                    wiz.preview_count = model.search_count(domain)
                except Exception:
                    wiz.preview_count = 0
            else:
                wiz.preview_count = 0

    @api.depends(
        'name', 'source_model_id', 'domain_filter', 'sync_mode',
        'interval_number', 'interval_type',
        'name_field_id', 'metadata_field_ids', 'parent_field_id',
        'date_field_id', 'period_config_id', 'dimension_field_ids',
        'preview_count',
    )
    def _compute_review_text(self):
        for wiz in self:
            wiz.review_text = wiz._build_review_text()

    def _build_review_text(self):
        """Generate a human-readable summary of the bridge configuration."""
        self.ensure_one()
        lines = []
        lines.append('Bridge Configuration Summary')
        lines.append('=' * 40)
        lines.append('')
        lines.append('Name: %s' % (self.name or '(not set)'))
        lines.append('Source Model: %s' % (
            self.source_model_id.name if self.source_model_id else '(not set)'
        ))
        lines.append('Domain Filter: %s' % (self.domain_filter or '[]'))
        lines.append('Matching Records: %d' % self.preview_count)
        lines.append('')

        # Sync
        lines.append('Sync Mode: %s' % (self.sync_mode or 'manual'))
        if self.sync_mode == 'scheduled':
            lines.append('Interval: every %d %s' % (
                self.interval_number, self.interval_type or 'days',
            ))
        lines.append('')

        # Mappings
        lines.append('Field Mappings:')
        if self.name_field_id:
            lines.append('  Name Field: %s (%s)' % (
                self.name_field_id.field_description, self.name_field_id.name,
            ))
        else:
            lines.append('  Name Field: (not set)')

        if self.metadata_field_ids:
            lines.append('  Metadata Fields:')
            for f in self.metadata_field_ids:
                lines.append('    - %s (%s)' % (f.field_description, f.name))
        else:
            lines.append('  Metadata Fields: (none)')

        if self.parent_field_id:
            lines.append('  Parent Field: %s (%s)' % (
                self.parent_field_id.field_description, self.parent_field_id.name,
            ))
        lines.append('')

        # Dimensions
        lines.append('Dimensions:')
        if self.date_field_id:
            lines.append('  Date Field: %s (%s)' % (
                self.date_field_id.field_description, self.date_field_id.name,
            ))
            if self.period_config_id:
                lines.append('  Period Config: %s' % self.period_config_id.name)
        if self.dimension_field_ids:
            for f in self.dimension_field_ids:
                lines.append('  Dimension: %s (%s)' % (f.field_description, f.name))
        if not self.date_field_id and not self.dimension_field_ids:
            lines.append('  (none configured)')

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def action_next_step(self):
        self.ensure_one()
        step_order = ['1_source', '2_mappings', '3_dimensions', '4_review']
        current_idx = step_order.index(self.step)
        if current_idx < len(step_order) - 1:
            self.step = step_order[current_idx + 1]
        return self._reopen()

    def action_prev_step(self):
        self.ensure_one()
        step_order = ['1_source', '2_mappings', '3_dimensions', '4_review']
        current_idx = step_order.index(self.step)
        if current_idx > 0:
            self.step = step_order[current_idx - 1]
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Create bridge
    # ------------------------------------------------------------------
    def action_create_bridge(self):
        """Create a setdb.data.bridge with mappings and dimensions from the wizard."""
        self.ensure_one()

        if not self.name:
            raise UserError('Please provide a bridge name.')
        if not self.source_model_id:
            raise UserError('Please select a source model.')
        if not self.name_field_id:
            raise UserError('Please select a name field for element names.')

        # Build mapping values
        mapping_vals = []
        sequence = 0

        # Name mapping
        mapping_vals.append((0, 0, {
            'source_field_id': self.name_field_id.id,
            'mapping_type': 'name',
            'sequence': sequence,
        }))
        sequence += 10

        # Metadata mappings
        for field in self.metadata_field_ids:
            mapping_vals.append((0, 0, {
                'source_field_id': field.id,
                'mapping_type': 'metadata',
                'metadata_key': field.name,
                'sequence': sequence,
            }))
            sequence += 10

        # Parent mapping
        if self.parent_field_id:
            mapping_vals.append((0, 0, {
                'source_field_id': self.parent_field_id.id,
                'mapping_type': 'parent',
                'sequence': sequence,
            }))
            sequence += 10

        # Build dimension values
        dimension_vals = []

        # Date dimension
        if self.date_field_id:
            dim_val = {
                'odoo_field_id': self.date_field_id.id,
                'auto_create_hierarchy': True,
            }
            if self.period_config_id:
                dim_val['period_config_id'] = self.period_config_id.id
            dimension_vals.append((0, 0, dim_val))

        # Other M2O dimensions
        for field in self.dimension_field_ids:
            dimension_vals.append((0, 0, {
                'odoo_field_id': field.id,
                'auto_create_hierarchy': True,
            }))

        # Create bridge
        bridge_vals = {
            'name': self.name,
            'source_model_id': self.source_model_id.id,
            'domain_filter': self.domain_filter or '[]',
            'sync_mode': self.sync_mode,
            'interval_number': self.interval_number,
            'interval_type': self.interval_type,
            'mapping_ids': mapping_vals,
            'dimension_ids': dimension_vals,
        }

        bridge = self.env['setdb.data.bridge'].create(bridge_vals)
        _logger.info(
            'Bridge "%s" created via wizard (id=%d, model=%s, %d mappings, %d dimensions).',
            bridge.name, bridge.id, self.source_model_id.model,
            len(mapping_vals), len(dimension_vals),
        )

        return {
            'type': 'ir.actions.act_window',
            'name': 'Data Bridge',
            'res_model': 'setdb.data.bridge',
            'res_id': bridge.id,
            'view_mode': 'form',
            'target': 'current',
        }
