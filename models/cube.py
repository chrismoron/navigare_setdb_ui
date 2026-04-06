import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBCube(models.Model):
    _name = 'setdb.cube'
    _description = 'SetDB OLAP Cube'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    description = fields.Text()
    row_hierarchy_id = fields.Many2one(
        'setdb.hierarchy', required=True, ondelete='restrict',
        string='Row Hierarchy',
    )
    column_hierarchy_id = fields.Many2one(
        'setdb.hierarchy', required=True, ondelete='restrict',
        string='Column Hierarchy',
    )
    filter_hierarchy_ids = fields.Many2many(
        'setdb.hierarchy', 'setdb_cube_filter_hierarchy_rel',
        'cube_id', 'hierarchy_id',
        string='Filter Hierarchies',
    )
    measure_ids = fields.One2many('setdb.cube.measure', 'cube_id', string='Measures')
    formula_ids = fields.One2many('setdb.cube.formula', 'cube_id', string='Formulas')
    active_filter_json = fields.Text(
        string='Active Filters (JSON)', default='{}',
        help='JSON dict: {hierarchy_id: [element_id, ...]}',
    )
    row_expand_state = fields.Text(
        string='Row Expand State', default='[]',
        help='JSON list of expanded row element IDs.',
    )
    column_expand_state = fields.Text(
        string='Column Expand State', default='[]',
        help='JSON list of expanded column element IDs.',
    )
    show_row_totals = fields.Boolean(default=True)
    show_col_totals = fields.Boolean(default=True)
    show_grand_total = fields.Boolean(default=True)
    default_row_depth = fields.Integer(default=1)
    default_col_depth = fields.Integer(default=1)
    auto_materialize = fields.Boolean(
        default=True,
        help='Automatically create materialized views for elements used in this cube.',
    )
    author_id = fields.Many2one(
        'res.users', default=lambda self: self.env.uid, readonly=True,
    )
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint('UNIQUE(name)', 'Cube name must be unique.')

    # ------------------------------------------------------------------
    # Expand-state helpers
    # ------------------------------------------------------------------

    def _get_visible_elements(self, hierarchy, expand_state_json, default_depth):
        """Return a list of element records that should be visible given
        the expand state and default depth."""
        self.ensure_one()
        expanded_ids = set(json.loads(expand_state_json or '[]'))
        root = hierarchy.root_id
        return self._collect_visible(root, expanded_ids, default_depth, current_depth=0)

    def _collect_visible(self, element, expanded_ids, default_depth, current_depth):
        """Recursively collect visible elements."""
        result = []
        children = element.members()
        if not children:
            # leaf / primitive — always visible when reached
            result.append(element)
            return result

        if current_depth < default_depth or element.id in expanded_ids:
            for child in children:
                result.extend(
                    self._collect_visible(child, expanded_ids, default_depth, current_depth + 1)
                )
        else:
            # collapsed — show the set element itself (aggregated)
            result.append(element)
        return result

    # ------------------------------------------------------------------
    # Grid computation
    # ------------------------------------------------------------------

    def compute_grid(self):
        """Compute the full OLAP grid for this cube.

        Returns:
            dict: {
                'rows': [{'id': int, 'name': str, 'depth': int}, ...],
                'columns': [{'id': int, 'name': str, 'depth': int}, ...],
                'measures': [{'id': int, 'name': str, 'key': str}, ...],
                'cells': {(row_id, col_id): {measure_key: value, ...}},
                'row_totals': {row_id: {measure_key: value}},
                'col_totals': {col_id: {measure_key: value}},
                'grand_total': {measure_key: value},
                'formulas': {formula_id: {element_id: value}},
            }
        """
        self.ensure_one()
        engine = self.env['setdb.cube.engine']
        formula_engine = self.env['setdb.formula.engine']

        # 1. Resolve visible rows and columns
        visible_rows = self._get_visible_elements(
            self.row_hierarchy_id, self.row_expand_state, self.default_row_depth,
        )
        visible_cols = self._get_visible_elements(
            self.column_hierarchy_id, self.column_expand_state, self.default_col_depth,
        )

        row_ids = [r.id for r in visible_rows]
        col_ids = [c.id for c in visible_cols]
        measures = self.measure_ids

        if not row_ids or not col_ids or not measures:
            return {
                'rows': [], 'columns': [], 'measures': [],
                'cells': {}, 'row_totals': {}, 'col_totals': {},
                'grand_total': {}, 'formulas': {},
            }

        # 2. Ensure materialized views exist
        if self.auto_materialize:
            all_element_ids = list(set(row_ids + col_ids))
            engine._ensure_materialized_views(all_element_ids)

        # 3. Bulk cell computation
        cells = engine.compute_cells(self, row_ids, col_ids, measures)

        # 4. Apply formulas
        formulas_result = {}
        for formula in self.formula_ids.sorted('sequence'):
            if formula.axis == 'row':
                # For each column, evaluate formula across row values
                for col_id in col_ids:
                    row_values = {}
                    for row in visible_rows:
                        key = (row.id, col_id)
                        cell = cells.get(key, {})
                        row_values[row.name.lower()] = cell.get(
                            measures[0].metadata_key, 0.0,
                        ) if measures else 0.0
                    try:
                        val = formula_engine.evaluate_formula(formula.formula_text, row_values)
                    except Exception:
                        val = 0.0
                    formulas_result.setdefault(formula.id, {})[col_id] = val
            elif formula.axis == 'column':
                for row_id in row_ids:
                    col_values = {}
                    for col in visible_cols:
                        key = (row_id, col.id)
                        cell = cells.get(key, {})
                        col_values[col.name.lower()] = cell.get(
                            measures[0].metadata_key, 0.0,
                        ) if measures else 0.0
                    try:
                        val = formula_engine.evaluate_formula(formula.formula_text, col_values)
                    except Exception:
                        val = 0.0
                    formulas_result.setdefault(formula.id, {})[row_id] = val

        # 5. Totals
        row_totals = {}
        col_totals = {}
        grand_total = {}
        if self.show_row_totals:
            row_totals = engine.compute_row_totals(cells, row_ids, col_ids, measures)
        if self.show_col_totals:
            col_totals = engine.compute_col_totals(cells, row_ids, col_ids, measures)
        if self.show_grand_total:
            grand_total = engine.compute_grand_total(cells, measures)

        return {
            'rows': [
                {'id': r.id, 'name': r.name, 'depth': r.depth()}
                for r in visible_rows
            ],
            'columns': [
                {'id': c.id, 'name': c.name, 'depth': c.depth()}
                for c in visible_cols
            ],
            'measures': [
                {'id': m.id, 'name': m.name, 'key': m.metadata_key}
                for m in measures
            ],
            'cells': {
                '%d_%d' % (k[0], k[1]): v for k, v in cells.items()
            },
            'row_totals': row_totals,
            'col_totals': col_totals,
            'grand_total': grand_total,
            'formulas': formulas_result,
        }

    # ------------------------------------------------------------------
    # Navigation operations
    # ------------------------------------------------------------------

    def drill_down(self, axis, element_id):
        """Expand an element on the given axis to show its children."""
        self.ensure_one()
        if axis == 'row':
            state = json.loads(self.row_expand_state or '[]')
            if element_id not in state:
                state.append(element_id)
            self.write({'row_expand_state': json.dumps(state)})
        elif axis == 'column':
            state = json.loads(self.column_expand_state or '[]')
            if element_id not in state:
                state.append(element_id)
            self.write({'column_expand_state': json.dumps(state)})
        else:
            raise UserError("Axis must be 'row' or 'column'.")
        return self.compute_grid()

    def roll_up(self, axis, element_id):
        """Collapse an element on the given axis."""
        self.ensure_one()
        if axis == 'row':
            state = json.loads(self.row_expand_state or '[]')
            if element_id in state:
                state.remove(element_id)
            self.write({'row_expand_state': json.dumps(state)})
        elif axis == 'column':
            state = json.loads(self.column_expand_state or '[]')
            if element_id in state:
                state.remove(element_id)
            self.write({'column_expand_state': json.dumps(state)})
        else:
            raise UserError("Axis must be 'row' or 'column'.")
        return self.compute_grid()

    def pivot(self):
        """Swap rows and columns."""
        self.ensure_one()
        self.write({
            'row_hierarchy_id': self.column_hierarchy_id.id,
            'column_hierarchy_id': self.row_hierarchy_id.id,
            'row_expand_state': self.column_expand_state,
            'column_expand_state': self.row_expand_state,
            'default_row_depth': self.default_col_depth,
            'default_col_depth': self.default_row_depth,
        })
        return self.compute_grid()

    def slice(self, hierarchy_id, element_id):
        """Apply a single-element filter on a filter hierarchy (slice).

        Args:
            hierarchy_id: int — ID of the filter hierarchy
            element_id: int — ID of the element to filter on
        """
        self.ensure_one()
        filters = json.loads(self.active_filter_json or '{}')
        filters[str(hierarchy_id)] = [element_id]
        self.write({'active_filter_json': json.dumps(filters)})
        return self.compute_grid()

    def dice(self, hierarchy_id, element_ids):
        """Apply a multi-element filter on a filter hierarchy (dice).

        Args:
            hierarchy_id: int — ID of the filter hierarchy
            element_ids: list of int — IDs of elements to include
        """
        self.ensure_one()
        filters = json.loads(self.active_filter_json or '{}')
        filters[str(hierarchy_id)] = element_ids
        self.write({'active_filter_json': json.dumps(filters)})
        return self.compute_grid()


class SetDBCubeMeasure(models.Model):
    _name = 'setdb.cube.measure'
    _description = 'SetDB Cube Measure'
    _order = 'sequence, id'

    cube_id = fields.Many2one(
        'setdb.cube', required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(required=True)
    metadata_key = fields.Char(
        required=True,
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
    format_string = fields.Char(default='#,##0.00')
    conditional_format_json = fields.Text(
        string='Conditional Format (JSON)',
        help='JSON list: [{"condition": ">1000", "style": "color:green"}, ...]',
    )
    sequence = fields.Integer(default=10)


class SetDBCubeFormula(models.Model):
    _name = 'setdb.cube.formula'
    _description = 'SetDB Cube Formula'
    _order = 'sequence, id'

    cube_id = fields.Many2one(
        'setdb.cube', required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(required=True)
    formula_text = fields.Text(
        required=True,
        help='Formula expression, e.g. "row:przychody - row:koszty"',
    )
    axis = fields.Selection([
        ('row', 'Row'),
        ('column', 'Column'),
    ], required=True, default='row')
    sequence = fields.Integer(default=10)
    style = fields.Selection([
        ('normal', 'Normal'),
        ('bold', 'Bold'),
        ('italic', 'Italic'),
        ('separator', 'Separator'),
    ], default='normal')
    is_percentage = fields.Boolean(default=False)


class SetDBCubeCellCache(models.Model):
    _name = 'setdb.cube.cell_cache'
    _description = 'SetDB Cube Cell Cache'
    _order = 'computed_at desc'

    cube_id = fields.Many2one(
        'setdb.cube', required=True, ondelete='cascade', index=True,
    )
    row_element_id = fields.Many2one(
        'setdb.element', required=True, ondelete='cascade', index=True,
        string='Row Element',
    )
    col_element_id = fields.Many2one(
        'setdb.element', required=True, ondelete='cascade', index=True,
        string='Column Element',
    )
    measure_id = fields.Many2one(
        'setdb.cube.measure', required=True, ondelete='cascade', index=True,
    )
    value = fields.Float(default=0.0)
    intersection_count = fields.Integer(
        default=0,
        help='Number of primitives in the intersection of row and column.',
    )
    is_stale = fields.Boolean(default=False, index=True)
    computed_at = fields.Datetime(default=fields.Datetime.now)

    _cell_unique = models.Constraint(
        'UNIQUE(cube_id, row_element_id, col_element_id, measure_id)',
        'Duplicate cell cache entry.',
    )

    @api.model
    def _cron_refresh_stale(self):
        """Cron: recompute stale cell cache entries."""
        stale = self.search([('is_stale', '=', True)], limit=500)
        if not stale:
            return
        for cube in stale.mapped('cube_id'):
            try:
                cube.compute_grid()
            except Exception:
                pass
        stale.write({'is_stale': False, 'computed_at': fields.Datetime.now()})
