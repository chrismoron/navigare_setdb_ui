import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBParameterWizard(models.TransientModel):
    _name = 'setdb.parameter.wizard'
    _description = 'SetDB Parameter Schema Builder Wizard'

    saved_query_id = fields.Many2one(
        'setdb.saved.query', string='Saved Query', required=True, ondelete='cascade',
    )
    line_ids = fields.One2many(
        'setdb.parameter.wizard.line', 'wizard_id', string='Parameters',
    )
    generated_json = fields.Text(
        string='Generated JSON', readonly=True, compute='_compute_generated_json',
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends(
        'line_ids', 'line_ids.param_name', 'line_ids.param_type',
        'line_ids.param_label', 'line_ids.param_default',
        'line_ids.param_required', 'line_ids.sequence',
    )
    def _compute_generated_json(self):
        for wiz in self:
            wiz.generated_json = wiz._build_parameters_json()

    def _build_parameters_json(self):
        """Build parameters_json from the wizard lines."""
        self.ensure_one()
        params = []
        for line in self.line_ids.sorted('sequence'):
            if not line.param_name:
                continue
            param = {
                'name': line.param_name,
                'type': line.param_type or 'text',
            }
            if line.param_label:
                param['label'] = line.param_label
            if line.param_default:
                param['default'] = line.param_default
            if line.param_required:
                param['required'] = True
            params.append(param)
        if not params:
            return '[]'
        return json.dumps(params, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Default: pre-populate lines from existing parameters_json
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        saved_query_id = res.get('saved_query_id') or self.env.context.get('default_saved_query_id')
        if saved_query_id and 'line_ids' in fields_list:
            saved_query = self.env['setdb.saved.query'].browse(saved_query_id)
            if saved_query.exists() and saved_query.parameters_json:
                try:
                    existing = json.loads(saved_query.parameters_json)
                    lines = []
                    for idx, param in enumerate(existing):
                        lines.append((0, 0, {
                            'param_name': param.get('name', ''),
                            'param_type': param.get('type', 'text'),
                            'param_label': param.get('label', ''),
                            'param_default': param.get('default', ''),
                            'param_required': param.get('required', False),
                            'sequence': idx * 10,
                        }))
                    res['line_ids'] = lines
                except (json.JSONDecodeError, TypeError):
                    pass
        return res

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_apply(self):
        """Write the generated JSON to the saved query's parameters_json."""
        self.ensure_one()
        if not self.saved_query_id:
            raise UserError('Please select a saved query.')

        generated = self._build_parameters_json()
        self.saved_query_id.write({'parameters_json': generated})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Parameters Updated',
                'message': 'Parameter schema for "%s" has been updated (%d parameters).' % (
                    self.saved_query_id.name,
                    len(self.line_ids.filtered('param_name')),
                ),
                'type': 'success',
                'sticky': False,
            },
        }


class SetDBParameterWizardLine(models.TransientModel):
    _name = 'setdb.parameter.wizard.line'
    _description = 'SetDB Parameter Wizard Line'
    _order = 'sequence, id'

    wizard_id = fields.Many2one(
        'setdb.parameter.wizard', required=True, ondelete='cascade',
    )
    param_name = fields.Char(string='Parameter Name', required=True)
    param_type = fields.Selection([
        ('element', 'Element'),
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('boolean', 'Boolean'),
    ], string='Type', default='text', required=True)
    param_label = fields.Char(string='Label')
    param_default = fields.Char(string='Default Value')
    param_required = fields.Boolean(string='Required', default=False)
    sequence = fields.Integer(default=10)
