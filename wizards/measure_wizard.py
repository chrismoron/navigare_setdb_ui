import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBMeasureWizard(models.TransientModel):
    _name = 'setdb.measure.wizard'
    _description = 'SetDB Cube Measure Builder Wizard'

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    cube_id = fields.Many2one(
        'setdb.cube', string='Cube', required=True, ondelete='cascade',
    )

    # ------------------------------------------------------------------
    # Measure definition
    # ------------------------------------------------------------------
    name = fields.Char(string='Measure Name', required=True)
    metadata_key = fields.Char(
        string='Metadata Key', required=True,
        help='Key in element metadata_json to aggregate.',
    )
    aggregation = fields.Selection([
        ('sum', 'Sum'),
        ('count', 'Count'),
        ('avg', 'Average'),
        ('min', 'Minimum'),
        ('max', 'Maximum'),
        ('count_distinct', 'Count Distinct'),
        ('median', 'Median'),
        ('variance', 'Variance'),
        ('stddev', 'Std Deviation'),
    ], default='sum', required=True)
    format_string = fields.Char(string='Format String', default='#,##0.00')

    # ------------------------------------------------------------------
    # Conditional formatting
    # ------------------------------------------------------------------
    conditional_format_type = fields.Selection([
        ('none', 'None'),
        ('heatmap', 'Heatmap'),
        ('threshold', 'Threshold'),
        ('custom', 'Custom Rules'),
    ], default='none', string='Conditional Format')

    heatmap_min_color = fields.Char(string='Heatmap Min Color', default='#ffffff')
    heatmap_max_color = fields.Char(string='Heatmap Max Color', default='#ff0000')

    threshold_value = fields.Float(string='Threshold Value')
    threshold_above_color = fields.Char(string='Above Threshold Color', default='#00ff00')
    threshold_below_color = fields.Char(string='Below Threshold Color', default='#ff0000')

    custom_rules_text = fields.Text(
        string='Custom Rules',
        help='JSON array of rules: [{"condition": ">1000", "style": "color:green"}, ...]',
    )

    # ------------------------------------------------------------------
    # Computed output
    # ------------------------------------------------------------------
    generated_format_json = fields.Text(
        string='Generated Format JSON', readonly=True,
        compute='_compute_generated_format_json',
    )
    available_keys = fields.Text(
        string='Available Metadata Keys', readonly=True,
        compute='_compute_available_keys',
    )

    # ------------------------------------------------------------------
    # Compute: available metadata keys
    # ------------------------------------------------------------------
    @api.depends('cube_id')
    def _compute_available_keys(self):
        for wiz in self:
            wiz.available_keys = wiz._scan_metadata_keys()

    def _scan_metadata_keys(self):
        """Scan metadata_json of elements in the cube's hierarchies to discover
        available metadata keys."""
        self.ensure_one()
        keys = set()
        if not self.cube_id:
            return ''

        # Collect elements from row and column hierarchies
        element_ids = []
        if self.cube_id.row_hierarchy_id and self.cube_id.row_hierarchy_id.root_id:
            root = self.cube_id.row_hierarchy_id.root_id
            try:
                primitives = root.flatten(max_depth=3)
                element_ids.extend(primitives[:200].ids)
            except Exception:
                pass

        if self.cube_id.column_hierarchy_id and self.cube_id.column_hierarchy_id.root_id:
            root = self.cube_id.column_hierarchy_id.root_id
            try:
                primitives = root.flatten(max_depth=3)
                element_ids.extend(primitives[:200].ids)
            except Exception:
                pass

        if not element_ids:
            return '(no elements found)'

        elements = self.env['setdb.element'].browse(element_ids[:400])
        for el in elements:
            if el.metadata_json:
                try:
                    meta = json.loads(el.metadata_json)
                    if isinstance(meta, dict):
                        keys.update(meta.keys())
                except (json.JSONDecodeError, TypeError):
                    pass

        if not keys:
            return '(no metadata keys found)'

        sorted_keys = sorted(keys)
        lines = ['Available metadata keys (%d found):' % len(sorted_keys)]
        for k in sorted_keys:
            lines.append('  - %s' % k)
        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Compute: conditional format JSON
    # ------------------------------------------------------------------
    @api.depends(
        'conditional_format_type', 'heatmap_min_color', 'heatmap_max_color',
        'threshold_value', 'threshold_above_color', 'threshold_below_color',
        'custom_rules_text',
    )
    def _compute_generated_format_json(self):
        for wiz in self:
            wiz.generated_format_json = wiz._build_format_json()

    def _build_format_json(self):
        """Build conditional_format_json from the wizard fields."""
        self.ensure_one()
        fmt_type = self.conditional_format_type

        if fmt_type == 'none' or not fmt_type:
            return ''

        if fmt_type == 'heatmap':
            config = {
                'type': 'heatmap',
                'min_color': self.heatmap_min_color or '#ffffff',
                'max_color': self.heatmap_max_color or '#ff0000',
            }
            return json.dumps([config], indent=2)

        if fmt_type == 'threshold':
            rules = [
                {
                    'condition': '>=%s' % self.threshold_value,
                    'style': 'background-color:%s' % (self.threshold_above_color or '#00ff00'),
                },
                {
                    'condition': '<%s' % self.threshold_value,
                    'style': 'background-color:%s' % (self.threshold_below_color or '#ff0000'),
                },
            ]
            return json.dumps(rules, indent=2)

        if fmt_type == 'custom':
            # Validate and pass through
            if self.custom_rules_text:
                try:
                    parsed = json.loads(self.custom_rules_text)
                    return json.dumps(parsed, indent=2)
                except (json.JSONDecodeError, TypeError):
                    return '[]  // Invalid JSON - please fix'
            return '[]'

        return ''

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_create(self):
        """Create a new setdb.cube.measure from the wizard."""
        self.ensure_one()
        if not self.name or not self.metadata_key:
            raise UserError('Please provide a measure name and metadata key.')

        format_json = self._build_format_json() or False

        measure = self.env['setdb.cube.measure'].create({
            'cube_id': self.cube_id.id,
            'name': self.name,
            'metadata_key': self.metadata_key,
            'aggregation': self.aggregation,
            'format_string': self.format_string,
            'conditional_format_json': format_json,
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Measure Created',
                'message': 'Measure "%s" (key: %s, agg: %s) added to cube "%s".' % (
                    measure.name, measure.metadata_key,
                    measure.aggregation, self.cube_id.name,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_preview(self):
        """Show a sample computation for the measure."""
        self.ensure_one()
        if not self.cube_id or not self.metadata_key:
            raise UserError('Please select a cube and metadata key.')

        # Gather sample values from row hierarchy primitives
        sample_values = []
        if self.cube_id.row_hierarchy_id and self.cube_id.row_hierarchy_id.root_id:
            try:
                primitives = self.cube_id.row_hierarchy_id.root_id.flatten(max_depth=3)
                for el in primitives[:100]:
                    if el.metadata_json:
                        try:
                            meta = json.loads(el.metadata_json)
                            if isinstance(meta, dict) and self.metadata_key in meta:
                                val = meta[self.metadata_key]
                                if isinstance(val, (int, float)):
                                    sample_values.append(val)
                                else:
                                    try:
                                        sample_values.append(float(val))
                                    except (ValueError, TypeError):
                                        pass
                        except (json.JSONDecodeError, TypeError):
                            pass
            except Exception:
                pass

        if not sample_values:
            message = 'No numeric values found for key "%s" in the sample elements.' % self.metadata_key
        else:
            agg = self.aggregation
            if agg == 'sum':
                result = sum(sample_values)
            elif agg == 'count':
                result = len(sample_values)
            elif agg == 'avg':
                result = sum(sample_values) / len(sample_values)
            elif agg == 'min':
                result = min(sample_values)
            elif agg == 'max':
                result = max(sample_values)
            elif agg == 'count_distinct':
                result = len(set(sample_values))
            elif agg == 'median':
                sorted_vals = sorted(sample_values)
                n = len(sorted_vals)
                if n % 2 == 0:
                    result = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
                else:
                    result = sorted_vals[n // 2]
            elif agg == 'variance':
                mean = sum(sample_values) / len(sample_values)
                result = sum((x - mean) ** 2 for x in sample_values) / len(sample_values)
            elif agg == 'stddev':
                mean = sum(sample_values) / len(sample_values)
                variance = sum((x - mean) ** 2 for x in sample_values) / len(sample_values)
                result = variance ** 0.5
            else:
                result = sum(sample_values)

            message = (
                'Sample: %d values found for key "%s"\n'
                'Aggregation (%s): %.4f'
            ) % (len(sample_values), self.metadata_key, agg, result)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Measure Preview',
                'message': message,
                'type': 'info',
                'sticky': True,
            },
        }
