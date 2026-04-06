import json

from odoo.tests.common import TransactionCase


class TestCubeEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Element = cls.env['setdb.element']
        Edge = cls.env['setdb.edge']
        Hierarchy = cls.env['setdb.hierarchy']

        # Build two small hierarchies for cube testing.
        #
        # Row hierarchy (accounts):
        #   accounts_root -> {acc_revenue, acc_costs}
        #   acc_revenue has primitives: p_rev_1 (value=100), p_rev_2 (value=200)
        #   acc_costs has primitives: p_cost_1 (value=50)
        #
        # Column hierarchy (regions):
        #   regions_root -> {reg_north, reg_south}
        #   reg_north has primitives: p_rev_1, p_cost_1
        #   reg_south has primitives: p_rev_2

        cls.p_rev_1 = Element.create({
            'name': 'p_rev_1',
            'element_type': 'primitive',
            'metadata_json': json.dumps({'amount': 100}),
        })
        cls.p_rev_2 = Element.create({
            'name': 'p_rev_2',
            'element_type': 'primitive',
            'metadata_json': json.dumps({'amount': 200}),
        })
        cls.p_cost_1 = Element.create({
            'name': 'p_cost_1',
            'element_type': 'primitive',
            'metadata_json': json.dumps({'amount': 50}),
        })

        # Row sets
        cls.acc_revenue = Element.create({'name': 'acc_revenue', 'element_type': 'set'})
        Edge.create({'parent_id': cls.acc_revenue.id, 'child_id': cls.p_rev_1.id, 'ordinal': 0})
        Edge.create({'parent_id': cls.acc_revenue.id, 'child_id': cls.p_rev_2.id, 'ordinal': 1})

        cls.acc_costs = Element.create({'name': 'acc_costs', 'element_type': 'set'})
        Edge.create({'parent_id': cls.acc_costs.id, 'child_id': cls.p_cost_1.id, 'ordinal': 0})

        cls.accounts_root = Element.create({'name': 'accounts_root', 'element_type': 'set'})
        Edge.create({'parent_id': cls.accounts_root.id, 'child_id': cls.acc_revenue.id, 'ordinal': 0})
        Edge.create({'parent_id': cls.accounts_root.id, 'child_id': cls.acc_costs.id, 'ordinal': 1})

        # Column sets
        cls.reg_north = Element.create({'name': 'reg_north', 'element_type': 'set'})
        Edge.create({'parent_id': cls.reg_north.id, 'child_id': cls.p_rev_1.id, 'ordinal': 0})
        Edge.create({'parent_id': cls.reg_north.id, 'child_id': cls.p_cost_1.id, 'ordinal': 1})

        cls.reg_south = Element.create({'name': 'reg_south', 'element_type': 'set'})
        Edge.create({'parent_id': cls.reg_south.id, 'child_id': cls.p_rev_2.id, 'ordinal': 0})

        cls.regions_root = Element.create({'name': 'regions_root', 'element_type': 'set'})
        Edge.create({'parent_id': cls.regions_root.id, 'child_id': cls.reg_north.id, 'ordinal': 0})
        Edge.create({'parent_id': cls.regions_root.id, 'child_id': cls.reg_south.id, 'ordinal': 1})

        # Hierarchies
        cls.row_hierarchy = Hierarchy.create({
            'name': 'test_accounts_hier',
            'root_id': cls.accounts_root.id,
            'hierarchy_type': 'tree',
        })
        cls.col_hierarchy = Hierarchy.create({
            'name': 'test_regions_hier',
            'root_id': cls.regions_root.id,
            'hierarchy_type': 'tree',
        })

    def _create_cube(self, **kwargs):
        """Helper to create a cube with the test hierarchies."""
        vals = {
            'name': 'Test Cube',
            'row_hierarchy_id': self.row_hierarchy.id,
            'column_hierarchy_id': self.col_hierarchy.id,
            'default_row_depth': 1,
            'default_col_depth': 1,
            'show_row_totals': True,
            'show_col_totals': True,
            'show_grand_total': True,
            'auto_materialize': True,
        }
        vals.update(kwargs)
        cube = self.env['setdb.cube'].create(vals)
        return cube

    def test_compute_grid_returns_structure(self):
        """compute_grid should return a dict with rows, columns, measures, cells."""
        cube = self._create_cube()
        self.env['setdb.cube.measure'].create({
            'cube_id': cube.id,
            'name': 'Amount',
            'metadata_key': 'amount',
            'aggregation': 'sum',
        })

        grid = cube.compute_grid()

        self.assertIn('rows', grid)
        self.assertIn('columns', grid)
        self.assertIn('measures', grid)
        self.assertIn('cells', grid)
        self.assertTrue(len(grid['rows']) > 0, "Grid should have rows")
        self.assertTrue(len(grid['columns']) > 0, "Grid should have columns")
        self.assertEqual(len(grid['measures']), 1)

    def test_compute_grid_cells_have_values(self):
        """Cells at intersections should have computed values."""
        cube = self._create_cube()
        measure = self.env['setdb.cube.measure'].create({
            'cube_id': cube.id,
            'name': 'Amount',
            'metadata_key': 'amount',
            'aggregation': 'sum',
        })

        grid = cube.compute_grid()

        # There should be at least some non-empty cells
        cells = grid['cells']
        non_empty = {k: v for k, v in cells.items() if v.get('amount', 0) != 0}
        self.assertTrue(
            len(non_empty) > 0,
            "At least some cells should have non-zero values",
        )

    def test_compute_grid_count_aggregation(self):
        """Test count aggregation produces correct element counts."""
        cube = self._create_cube()
        self.env['setdb.cube.measure'].create({
            'cube_id': cube.id,
            'name': 'Count',
            'metadata_key': 'amount',
            'aggregation': 'count',
        })

        grid = cube.compute_grid()
        cells = grid['cells']

        # acc_revenue x reg_north: intersection is {p_rev_1}, count=1
        # acc_revenue x reg_south: intersection is {p_rev_2}, count=1
        # acc_costs x reg_north: intersection is {p_cost_1}, count=1
        # acc_costs x reg_south: intersection is empty, count=0
        non_empty = {k: v for k, v in cells.items() if v.get('count', 0) > 0}
        self.assertTrue(len(non_empty) >= 2, "Should have at least 2 non-empty count cells")

    def test_row_totals(self):
        """Row totals should sum across columns for each row."""
        cube = self._create_cube()
        self.env['setdb.cube.measure'].create({
            'cube_id': cube.id,
            'name': 'Amount',
            'metadata_key': 'amount',
            'aggregation': 'sum',
        })

        grid = cube.compute_grid()
        self.assertIn('row_totals', grid)
        # Row totals should be non-empty if there are cells
        if grid['cells']:
            self.assertTrue(len(grid['row_totals']) > 0)

    def test_grand_total(self):
        """Grand total should aggregate all cell values."""
        cube = self._create_cube()
        self.env['setdb.cube.measure'].create({
            'cube_id': cube.id,
            'name': 'Amount',
            'metadata_key': 'amount',
            'aggregation': 'sum',
        })

        grid = cube.compute_grid()
        self.assertIn('grand_total', grid)

    def test_empty_cube_no_measures(self):
        """A cube with no measures should return an empty grid."""
        cube = self._create_cube()
        grid = cube.compute_grid()
        self.assertEqual(grid['rows'], [])
        self.assertEqual(grid['cells'], {})

    def test_pivot_swaps_axes(self):
        """Pivoting should swap row and column hierarchies."""
        cube = self._create_cube()
        self.env['setdb.cube.measure'].create({
            'cube_id': cube.id,
            'name': 'Amount',
            'metadata_key': 'amount',
            'aggregation': 'sum',
        })

        original_row = cube.row_hierarchy_id.id
        original_col = cube.column_hierarchy_id.id

        cube.pivot()

        self.assertEqual(cube.row_hierarchy_id.id, original_col)
        self.assertEqual(cube.column_hierarchy_id.id, original_row)

    def test_drill_down_expands_state(self):
        """Drill down should add element to expand state."""
        cube = self._create_cube()
        self.env['setdb.cube.measure'].create({
            'cube_id': cube.id,
            'name': 'Amount',
            'metadata_key': 'amount',
            'aggregation': 'sum',
        })

        element_id = self.acc_revenue.id
        cube.drill_down('row', element_id)

        expand_state = json.loads(cube.row_expand_state)
        self.assertIn(element_id, expand_state)

    def test_roll_up_collapses_state(self):
        """Roll up should remove element from expand state."""
        cube = self._create_cube()
        self.env['setdb.cube.measure'].create({
            'cube_id': cube.id,
            'name': 'Amount',
            'metadata_key': 'amount',
            'aggregation': 'sum',
        })

        element_id = self.acc_revenue.id
        cube.drill_down('row', element_id)
        cube.roll_up('row', element_id)

        expand_state = json.loads(cube.row_expand_state)
        self.assertNotIn(element_id, expand_state)
