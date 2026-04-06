import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBFormulaWizard(models.TransientModel):
    _name = 'setdb.formula.wizard'
    _description = 'SetDB Cube Formula Builder Wizard'

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------
    cube_id = fields.Many2one(
        'setdb.cube', string='Cube', required=True, ondelete='cascade',
    )
    formula_name = fields.Char(string='Formula Name', required=True)

    # ------------------------------------------------------------------
    # Formula type
    # ------------------------------------------------------------------
    formula_type = fields.Selection([
        ('simple_math', 'Simple Math (A op B)'),
        ('row_reference', 'Row Reference Calculation'),
        ('percentage', 'Percentage Of'),
        ('custom', 'Custom Formula'),
    ], string='Formula Type', default='simple_math', required=True)

    # ------------------------------------------------------------------
    # Row references (for row_reference and simple_math types)
    # ------------------------------------------------------------------
    row_ref_1_id = fields.Many2one(
        'setdb.element', string='First Row Element',
        help='First element reference for the formula (e.g. row:revenue).',
    )
    row_ref_2_id = fields.Many2one(
        'setdb.element', string='Second Row Element',
        help='Second element reference for the formula (e.g. row:costs).',
    )

    # ------------------------------------------------------------------
    # Math operator (for simple_math)
    # ------------------------------------------------------------------
    math_operator = fields.Selection([
        ('+', 'Add (+)'),
        ('-', 'Subtract (-)'),
        ('*', 'Multiply (*)'),
        ('/', 'Divide (/)'),
    ], string='Operator', default='+')

    # ------------------------------------------------------------------
    # Custom formula text
    # ------------------------------------------------------------------
    custom_formula = fields.Text(
        string='Custom Formula',
        help='Free-text formula expression, e.g. "row:revenue - row:costs".',
    )

    # ------------------------------------------------------------------
    # Percentage
    # ------------------------------------------------------------------
    percentage_of_id = fields.Many2one(
        'setdb.element', string='Percentage Of',
        help='Element to use as the denominator for percentage calculation.',
    )

    # ------------------------------------------------------------------
    # Display options
    # ------------------------------------------------------------------
    axis = fields.Selection([
        ('row', 'Row'),
        ('column', 'Column'),
    ], default='row', required=True)

    style = fields.Selection([
        ('normal', 'Normal'),
        ('bold', 'Bold'),
        ('italic', 'Italic'),
        ('separator', 'Separator'),
    ], default='normal')

    # ------------------------------------------------------------------
    # Computed output
    # ------------------------------------------------------------------
    generated_formula = fields.Text(
        string='Generated Formula', readonly=True,
        compute='_compute_generated_formula',
    )
    preview_value = fields.Float(
        string='Preview Value', readonly=True,
    )

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    @api.depends(
        'formula_type', 'row_ref_1_id', 'row_ref_2_id',
        'math_operator', 'custom_formula', 'percentage_of_id',
    )
    def _compute_generated_formula(self):
        for wiz in self:
            wiz.generated_formula = wiz._build_formula_text()

    def _build_formula_text(self):
        """Build the formula text from wizard fields."""
        self.ensure_one()
        ftype = self.formula_type

        def _row_ref(element):
            if not element:
                return '?'
            return 'row:%s' % element.name.lower().replace(' ', '_')

        if ftype == 'simple_math':
            ref1 = _row_ref(self.row_ref_1_id)
            ref2 = _row_ref(self.row_ref_2_id)
            op = self.math_operator or '+'
            return '%s %s %s' % (ref1, op, ref2)

        if ftype == 'row_reference':
            ref1 = _row_ref(self.row_ref_1_id)
            ref2 = _row_ref(self.row_ref_2_id)
            if ref2 and ref2 != '?':
                return '%s - %s' % (ref1, ref2)
            return ref1

        if ftype == 'percentage':
            ref1 = _row_ref(self.row_ref_1_id)
            denom = _row_ref(self.percentage_of_id)
            return '(%s / %s) * 100' % (ref1, denom)

        if ftype == 'custom':
            return self.custom_formula or ''

        return ''

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_preview(self):
        """Compute a sample value using the formula engine with dummy data."""
        self.ensure_one()
        formula_text = self._build_formula_text()
        if not formula_text:
            raise UserError('Please complete the formula configuration.')

        # Build sample values from cube's row hierarchy children
        sample_values = {}
        if self.cube_id and self.cube_id.row_hierarchy_id:
            root = self.cube_id.row_hierarchy_id.root_id
            for child in root.members():
                sample_values[child.name.lower().replace(' ', '_')] = 100.0

        try:
            engine = self.env['setdb.formula.engine']
            result = engine.evaluate_formula(formula_text, sample_values)
            self.preview_value = float(result)
        except Exception as e:
            _logger.warning('Formula preview failed: %s', e)
            self.preview_value = 0.0

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_create(self):
        """Create a new setdb.cube.formula record from the wizard."""
        self.ensure_one()
        formula_text = self._build_formula_text()
        if not formula_text:
            raise UserError('Please complete the formula configuration.')

        formula = self.env['setdb.cube.formula'].create({
            'cube_id': self.cube_id.id,
            'name': self.formula_name,
            'formula_text': formula_text,
            'axis': self.axis,
            'style': self.style,
            'is_percentage': self.formula_type == 'percentage',
        })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Formula Created',
                'message': 'Formula "%s" has been added to cube "%s".' % (
                    formula.name, self.cube_id.name,
                ),
                'type': 'success',
                'sticky': False,
            },
        }

    def action_insert(self):
        """Insert formula into the existing cube (same as create, provided
        for semantic clarity when triggered from the cube form)."""
        return self.action_create()
