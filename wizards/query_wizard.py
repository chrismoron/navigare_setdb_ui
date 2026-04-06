import logging
import time

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Operations that require a second operand
_BINARY_OPS = {'union', 'intersect', 'difference', 'symmetric_diff'}


class SetDBQueryWizard(models.TransientModel):
    _name = 'setdb.query.wizard'
    _description = 'SetDB SetQL Query Builder Wizard'

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------
    step = fields.Selection([
        ('1_operation', 'Operation'),
        ('2_operands', 'Operands'),
        ('3_options', 'Options'),
        ('4_preview', 'Preview'),
    ], default='1_operation', required=True)

    # ------------------------------------------------------------------
    # Operation
    # ------------------------------------------------------------------
    operation = fields.Selection([
        ('flatten', 'FLATTEN'),
        ('members', 'MEMBERS'),
        ('union', 'UNION'),
        ('intersect', 'INTERSECT'),
        ('difference', 'DIFFERENCE'),
        ('symmetric_diff', 'SYMMETRIC DIFFERENCE'),
        ('complement', 'COMPLEMENT'),
        ('ancestors', 'ANCESTORS'),
        ('reachable', 'REACHABLE'),
        ('find', 'FIND'),
    ], string='Operation', default='flatten')

    operation_description = fields.Char(
        string='Operation Description', compute='_compute_operation_description',
    )

    # ------------------------------------------------------------------
    # Operands
    # ------------------------------------------------------------------
    operand_1_id = fields.Many2one(
        'setdb.element', string='First Operand',
        help='Primary element for the operation.',
    )
    operand_2_id = fields.Many2one(
        'setdb.element', string='Second Operand',
        help='Second element (for binary operations like UNION, INTERSECT, etc.).',
    )
    operand_3_id = fields.Many2one(
        'setdb.element', string='Omega / Universe',
        help='Universe set for COMPLEMENT ... WITHIN.',
    )

    # ------------------------------------------------------------------
    # Operation-specific options
    # ------------------------------------------------------------------
    max_depth = fields.Integer(
        string='Max Depth',
        help='Maximum recursion depth for FLATTEN / REACHABLE.',
    )

    # FIND options
    find_field = fields.Selection([
        ('name', 'Name'),
        ('element_type', 'Element Type'),
        ('cardinality', 'Cardinality'),
        ('depth', 'Depth'),
    ], string='Find Field')
    find_operator = fields.Selection([
        ('=', '='),
        ('!=', '!='),
        ('>', '>'),
        ('<', '<'),
        ('>=', '>='),
        ('<=', '<='),
        ('like', 'LIKE'),
    ], string='Find Operator', default='=')
    find_value = fields.Char(string='Find Value')

    # REACHABLE option
    via_element_id = fields.Many2one(
        'setdb.element', string='Via Element',
        help='Intermediate element for REACHABLE ... VIA.',
    )

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------
    generated_query = fields.Text(
        string='Generated Query', readonly=True, compute='_compute_generated_query',
    )
    preview_result_text = fields.Text(string='Preview Results', readonly=True)
    preview_count = fields.Integer(string='Result Count', readonly=True)

    # ------------------------------------------------------------------
    # Save options
    # ------------------------------------------------------------------
    target_saved_query_id = fields.Many2one(
        'setdb.saved.query', string='Update Existing Query',
        help='If set, the generated query will overwrite this saved query.',
    )
    save_as_name = fields.Char(
        string='Save As Name',
        help='If set, create a new saved query with this name.',
    )

    # ------------------------------------------------------------------
    # Computed: operation_description
    # ------------------------------------------------------------------
    _OPERATION_DESCRIPTIONS = {
        'flatten': 'Recursively expand a set, returning all primitive elements.',
        'members': 'Return the direct members of a set.',
        'union': 'Combine two sets, returning all elements from both.',
        'intersect': 'Return elements common to both sets.',
        'difference': 'Return elements in the first set but not in the second.',
        'symmetric_diff': 'Return elements in either set but not in both.',
        'complement': 'Return elements not in the given set (relative to a universe).',
        'ancestors': 'Return all ancestor sets that contain the given element.',
        'reachable': 'Find elements reachable from a starting element.',
        'find': 'Search for elements matching a condition.',
    }

    @api.depends('operation')
    def _compute_operation_description(self):
        for wiz in self:
            wiz.operation_description = self._OPERATION_DESCRIPTIONS.get(wiz.operation, '')

    # ------------------------------------------------------------------
    # Computed: generated_query
    # ------------------------------------------------------------------
    @api.depends(
        'operation', 'operand_1_id', 'operand_2_id', 'operand_3_id',
        'max_depth', 'find_field', 'find_operator', 'find_value',
        'via_element_id',
    )
    def _compute_generated_query(self):
        for wiz in self:
            wiz.generated_query = wiz._build_query_text()

    def _build_query_text(self):
        """Build a SetQL query string from the wizard fields."""
        self.ensure_one()
        op = self.operation
        if not op:
            return ''

        ref1 = self.operand_1_id.name if self.operand_1_id else ''
        ref2 = self.operand_2_id.name if self.operand_2_id else ''
        ref3 = self.operand_3_id.name if self.operand_3_id else ''

        # Quote element names that contain spaces
        def q(name):
            if not name:
                return '""'
            if ' ' in name:
                return '"%s"' % name
            return name

        if op == 'flatten':
            query = 'FLATTEN %s' % q(ref1)
            if self.max_depth and self.max_depth > 0:
                query += ' MAX DEPTH %d' % self.max_depth
            return query

        if op == 'members':
            return 'MEMBERS %s' % q(ref1)

        if op == 'union':
            return 'UNION(%s, %s)' % (q(ref1), q(ref2))

        if op == 'intersect':
            return 'INTERSECT(%s, %s)' % (q(ref1), q(ref2))

        if op == 'difference':
            return 'DIFFERENCE(%s, %s)' % (q(ref1), q(ref2))

        if op == 'symmetric_diff':
            return 'SYMMETRIC_DIFF(%s, %s)' % (q(ref1), q(ref2))

        if op == 'complement':
            query = 'COMPLEMENT %s' % q(ref1)
            if ref3:
                query += ' WITHIN %s' % q(ref3)
            return query

        if op == 'ancestors':
            return 'ANCESTORS %s' % q(ref1)

        if op == 'reachable':
            query = 'REACHABLE FROM %s' % q(ref1)
            if self.via_element_id:
                query += ' VIA %s' % q(self.via_element_id.name)
            if self.max_depth and self.max_depth > 0:
                query += ' MAX DEPTH %d' % self.max_depth
            return query

        if op == 'find':
            if self.find_field and self.find_operator and self.find_value:
                return 'FIND WHERE %s %s %s' % (
                    self.find_field,
                    self.find_operator,
                    '"%s"' % self.find_value if self.find_operator == 'like' else self.find_value,
                )
            return 'FIND WHERE ...'

        return ''

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def action_next_step(self):
        self.ensure_one()
        step_order = ['1_operation', '2_operands', '3_options', '4_preview']
        current_idx = step_order.index(self.step)
        if current_idx < len(step_order) - 1:
            self.step = step_order[current_idx + 1]
        return self._reopen()

    def action_prev_step(self):
        self.ensure_one()
        step_order = ['1_operation', '2_operands', '3_options', '4_preview']
        current_idx = step_order.index(self.step)
        if current_idx > 0:
            self.step = step_order[current_idx - 1]
        return self._reopen()

    def _reopen(self):
        """Return an action that reopens this wizard in a dialog."""
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    # ------------------------------------------------------------------
    # Preview / Execute
    # ------------------------------------------------------------------
    def action_preview(self):
        """Execute the generated query and populate preview fields."""
        self.ensure_one()
        query_text = self._build_query_text()
        if not query_text or query_text.endswith('...'):
            raise UserError('Please complete all required fields before previewing.')

        executor = self.env['setdb.query.executor']
        t0 = time.monotonic()
        try:
            result = executor.execute(query_text)
        except Exception as e:
            self.write({
                'preview_result_text': 'Error: %s' % str(e),
                'preview_count': 0,
            })
            return self._reopen()

        elapsed_ms = (time.monotonic() - t0) * 1000

        if hasattr(result, 'ids'):
            count = len(result)
            names = result[:50].mapped('name')
            text_lines = ['Query executed in %.1f ms' % elapsed_ms, '']
            text_lines.append('Results (%d elements):' % count)
            for n in names:
                text_lines.append('  - %s' % n)
            if count > 50:
                text_lines.append('  ... and %d more' % (count - 50))
            self.write({
                'preview_result_text': '\n'.join(text_lines),
                'preview_count': count,
            })
        else:
            self.write({
                'preview_result_text': 'Result: %s' % str(result),
                'preview_count': 0,
            })
        return self._reopen()

    def action_execute(self):
        """Execute the query and return an action showing results."""
        self.ensure_one()
        query_text = self._build_query_text()
        if not query_text or query_text.endswith('...'):
            raise UserError('Please complete all required fields before executing.')

        executor = self.env['setdb.query.executor']
        result = executor.execute(query_text)

        if hasattr(result, 'ids') and result.ids:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Query Results',
                'res_model': 'setdb.element',
                'view_mode': 'list,form',
                'domain': [('id', 'in', result.ids)],
                'target': 'current',
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Query Executed',
                'message': 'The query returned no results.',
                'type': 'warning',
                'sticky': False,
            },
        }

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def action_save(self):
        """Save the generated query as a new or existing saved query."""
        self.ensure_one()
        query_text = self._build_query_text()
        if not query_text or query_text.endswith('...'):
            raise UserError('Please complete all required fields before saving.')

        if self.target_saved_query_id:
            self.target_saved_query_id.write({'query_text': query_text})
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Query Updated',
                    'message': 'Saved query "%s" has been updated.' % self.target_saved_query_id.name,
                    'type': 'success',
                    'sticky': False,
                },
            }

        if self.save_as_name:
            saved = self.env['setdb.saved.query'].create({
                'name': self.save_as_name,
                'query_text': query_text,
            })
            return {
                'type': 'ir.actions.act_window',
                'name': 'Saved Query',
                'res_model': 'setdb.saved.query',
                'res_id': saved.id,
                'view_mode': 'form',
                'target': 'current',
            }

        raise UserError('Please specify a name for the new query or select an existing query to update.')

    def action_copy_to_clipboard(self):
        """Return a client action that copies the query text to clipboard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Query Copied',
                'message': self._build_query_text() or '',
                'type': 'info',
                'sticky': True,
            },
        }
