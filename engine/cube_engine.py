import json
import logging
import statistics

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# SQL aggregation functions supported natively
_SQL_AGGREGATIONS = {'sum', 'count', 'avg', 'min', 'max', 'count_distinct'}
# Aggregations that require Python-level computation
_PYTHON_AGGREGATIONS = {'median', 'variance', 'stddev'}


class SetDBCubeEngine(models.AbstractModel):
    _name = 'setdb.cube.engine'
    _description = 'SetDB Cube Computation Engine'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def compute_cells(self, cube, row_ids, col_ids, measures):
        """Bulk-compute cell values for all (row, col, measure) combinations.

        Args:
            cube: setdb.cube record
            row_ids: list of int — row element IDs
            col_ids: list of int — column element IDs
            measures: recordset of setdb.cube.measure

        Returns:
            dict: {(row_id, col_id): {measure_key: value, 'count': int}}
        """
        if not row_ids or not col_ids or not measures:
            return {}

        all_element_ids = list(set(row_ids + col_ids))
        self._ensure_materialized_views(all_element_ids)

        # Separate SQL-capable vs Python-level aggregations
        sql_measures = measures.filtered(lambda m: m.aggregation in _SQL_AGGREGATIONS)
        python_measures = measures.filtered(lambda m: m.aggregation in _PYTHON_AGGREGATIONS)

        cells = {}

        # --- SQL bulk computation ---
        if sql_measures:
            cells = self._compute_cells_sql(row_ids, col_ids, sql_measures)

        # --- Python-level computation for median/variance/stddev ---
        if python_measures:
            python_cells = self._compute_cells_python(row_ids, col_ids, python_measures)
            for key, vals in python_cells.items():
                cells.setdefault(key, {}).update(vals)

        return cells

    @api.model
    def compute_row_totals(self, cells, row_ids, col_ids, measures):
        """Compute totals per row (summing across columns).

        Returns:
            dict: {row_id: {measure_key: value}}
        """
        result = {}
        for row_id in row_ids:
            totals = {}
            for measure in measures:
                key = measure.metadata_key
                agg = measure.aggregation
                values = []
                for col_id in col_ids:
                    cell = cells.get((row_id, col_id), {})
                    if key in cell:
                        values.append(cell[key])
                totals[key] = self._aggregate_values(values, agg)
            result[row_id] = totals
        return result

    @api.model
    def compute_col_totals(self, cells, row_ids, col_ids, measures):
        """Compute totals per column (summing across rows).

        Returns:
            dict: {col_id: {measure_key: value}}
        """
        result = {}
        for col_id in col_ids:
            totals = {}
            for measure in measures:
                key = measure.metadata_key
                agg = measure.aggregation
                values = []
                for row_id in row_ids:
                    cell = cells.get((row_id, col_id), {})
                    if key in cell:
                        values.append(cell[key])
                totals[key] = self._aggregate_values(values, agg)
            result[col_id] = totals
        return result

    @api.model
    def compute_grand_total(self, cells, measures):
        """Compute overall grand totals across all cells.

        Returns:
            dict: {measure_key: value}
        """
        result = {}
        for measure in measures:
            key = measure.metadata_key
            agg = measure.aggregation
            values = []
            for cell in cells.values():
                if key in cell:
                    values.append(cell[key])
            result[key] = self._aggregate_values(values, agg)
        return result

    @api.model
    def _ensure_materialized_views(self, element_ids):
        """Ensure materialized views exist for all given element IDs.

        For elements that are sets without a fresh materialized view,
        compute and cache the flatten result.
        """
        if not element_ids:
            return

        Element = self.env['setdb.element']
        MatView = self.env['setdb.materialized_view']

        # Find elements that are sets (non-primitives)
        elements = Element.browse(element_ids).filtered(
            lambda e: e.element_type != 'primitive'
        )
        if not elements:
            return

        # Check which already have fresh materialized views
        existing = MatView.search([
            ('source_id', 'in', elements.ids),
            ('is_stale', '=', False),
        ])
        existing_source_ids = set(existing.mapped('source_id').ids)
        missing = elements.filtered(lambda e: e.id not in existing_source_ids)

        if not missing:
            return

        _logger.info("Creating materialized views for %d elements.", len(missing))
        create_vals = []
        for elem in missing:
            primitives = elem._compute_flatten(None)
            create_vals.append({
                'source_id': elem.id,
                'primitive_ids': [fields.Command.set(primitives.ids)],
                'computed_at': fields.Datetime.now(),
                'last_accessed': fields.Datetime.now(),
                'access_count': 1,
                'size_estimate': len(primitives),
            })

        if create_vals:
            # Some sources may already have stale views — remove them first
            stale = MatView.search([
                ('source_id', 'in', missing.ids),
            ])
            if stale:
                stale.unlink()
            MatView.create(create_vals)

    # ------------------------------------------------------------------
    # Internal: SQL bulk computation
    # ------------------------------------------------------------------

    @api.model
    def _compute_cells_sql(self, row_ids, col_ids, measures):
        """Use SQL to compute cell values via materialized view intersection.

        The approach:
        1. For each (row, col) pair, find the intersection of their
           materialized primitive sets.
        2. From that intersection, extract metadata values and aggregate.

        Returns:
            dict: {(row_id, col_id): {measure_key: value, 'count': int}}
        """
        # The materialized view stores primitives in setdb_matview_primitive_rel
        # (matview_id, element_id).
        # We join row matviews with col matviews on element_id to get intersections.

        # Build aggregation SQL fragments
        agg_selects = []
        for measure in measures:
            key = measure.metadata_key
            agg = measure.aggregation
            # Metadata is stored as JSON in setdb_element.metadata_json
            # We extract the value using JSON operators
            json_extract = "CAST(el.metadata_json::json->>'%s' AS DOUBLE PRECISION)" % key
            if agg == 'count_distinct':
                agg_selects.append(
                    "COUNT(DISTINCT %s) AS \"%s\"" % (json_extract, key)
                )
            elif agg == 'count':
                agg_selects.append(
                    "COUNT(%s) AS \"%s\"" % (json_extract, key)
                )
            else:
                agg_selects.append(
                    "%s(%s) AS \"%s\"" % (agg.upper(), json_extract, key)
                )

        agg_sql = ', '.join(agg_selects)
        if not agg_sql:
            return {}

        query = """
            SELECT
                rmv.source_id AS row_id,
                cmv.source_id AS col_id,
                COUNT(rp.element_id) AS intersection_count,
                %(agg_sql)s
            FROM setdb_matview_primitive_rel rp
            JOIN setdb_materialized_view rmv ON rmv.id = rp.matview_id
            JOIN setdb_matview_primitive_rel cp ON cp.element_id = rp.element_id
            JOIN setdb_materialized_view cmv ON cmv.id = cp.matview_id
            JOIN setdb_element el ON el.id = rp.element_id
            WHERE rmv.source_id = ANY(%%s)
              AND cmv.source_id = ANY(%%s)
              AND rmv.is_stale = FALSE
              AND cmv.is_stale = FALSE
              AND el.active = TRUE
            GROUP BY rmv.source_id, cmv.source_id
        """ % {'agg_sql': agg_sql}

        # Handle primitives — they won't have materialized views.
        # For primitives, we need a different strategy: the primitive IS its own set.
        # We handle this by checking if elements are primitives and treating them specially.
        Element = self.env['setdb.element']

        # Partition into primitives and sets
        all_row_elements = Element.browse(row_ids)
        all_col_elements = Element.browse(col_ids)
        prim_row_ids = [e.id for e in all_row_elements if e.element_type == 'primitive']
        set_row_ids = [e.id for e in all_row_elements if e.element_type != 'primitive']
        prim_col_ids = [e.id for e in all_col_elements if e.element_type == 'primitive']
        set_col_ids = [e.id for e in all_col_elements if e.element_type != 'primitive']

        cells = {}

        # Case 1: set rows x set cols — use materialized view intersection
        if set_row_ids and set_col_ids:
            self.env.cr.execute(query, (set_row_ids, set_col_ids))
            for row in self.env.cr.dictfetchall():
                key = (row['row_id'], row['col_id'])
                cell = {'count': row['intersection_count']}
                for measure in measures:
                    val = row.get(measure.metadata_key)
                    cell[measure.metadata_key] = float(val) if val is not None else 0.0
                cells[key] = cell

        # Case 2: primitive rows x set cols
        if prim_row_ids and set_col_ids:
            self._compute_primitive_vs_set(prim_row_ids, set_col_ids, measures, cells, 'row')

        # Case 3: set rows x primitive cols
        if set_row_ids and prim_col_ids:
            self._compute_primitive_vs_set(prim_col_ids, set_row_ids, measures, cells, 'col')

        # Case 4: primitive rows x primitive cols
        if prim_row_ids and prim_col_ids:
            self._compute_primitive_vs_primitive(prim_row_ids, prim_col_ids, measures, cells)

        return cells

    @api.model
    def _compute_primitive_vs_set(self, prim_ids, set_ids, measures, cells, prim_axis):
        """Compute cells where one axis is primitive elements and the other is sets.

        A primitive is in a set's intersection iff it appears in the set's
        materialized view primitives.
        """
        agg_selects = []
        for measure in measures:
            key = measure.metadata_key
            json_extract = "CAST(el.metadata_json::json->>'%s' AS DOUBLE PRECISION)" % key
            agg_selects.append("%s AS \"%s\"" % (json_extract, key))

        agg_sql = ', '.join(agg_selects)

        query = """
            SELECT
                el.id AS prim_id,
                mv.source_id AS set_id,
                %(agg_sql)s
            FROM setdb_matview_primitive_rel mp
            JOIN setdb_materialized_view mv ON mv.id = mp.matview_id
            JOIN setdb_element el ON el.id = mp.element_id
            WHERE mp.element_id = ANY(%%s)
              AND mv.source_id = ANY(%%s)
              AND mv.is_stale = FALSE
              AND el.active = TRUE
        """ % {'agg_sql': agg_sql}

        self.env.cr.execute(query, (prim_ids, set_ids))
        for row in self.env.cr.dictfetchall():
            if prim_axis == 'row':
                key = (row['prim_id'], row['set_id'])
            else:
                key = (row['set_id'], row['prim_id'])
            cell = {'count': 1}
            for measure in measures:
                val = row.get(measure.metadata_key)
                cell[measure.metadata_key] = float(val) if val is not None else 0.0
            cells[key] = cell

    @api.model
    def _compute_primitive_vs_primitive(self, row_prim_ids, col_prim_ids, measures, cells):
        """Compute cells where both axes are primitive elements.

        Two primitives intersect only if they are the same element.
        """
        common_ids = set(row_prim_ids) & set(col_prim_ids)
        if not common_ids:
            return

        Element = self.env['setdb.element']
        for elem_id in common_ids:
            elem = Element.browse(elem_id)
            if not elem.metadata_json:
                continue
            try:
                meta = json.loads(elem.metadata_json)
            except (json.JSONDecodeError, TypeError):
                continue
            cell = {'count': 1}
            for measure in measures:
                val = meta.get(measure.metadata_key, 0.0)
                try:
                    cell[measure.metadata_key] = float(val)
                except (TypeError, ValueError):
                    cell[measure.metadata_key] = 0.0
            cells[(elem_id, elem_id)] = cell

    # ------------------------------------------------------------------
    # Internal: Python-level computation for advanced aggregations
    # ------------------------------------------------------------------

    @api.model
    def _compute_cells_python(self, row_ids, col_ids, measures):
        """Compute median, variance, stddev using Python.

        Fetches raw intersection primitive values and computes in Python.
        """
        cells = {}

        for row_id in row_ids:
            for col_id in col_ids:
                # Get intersection primitives
                prim_ids = self._get_intersection_primitives(row_id, col_id)
                if not prim_ids:
                    continue

                # Fetch metadata for all primitives
                Element = self.env['setdb.element']
                prims = Element.browse(prim_ids)

                cell = {'count': len(prim_ids)}
                for measure in measures:
                    values = []
                    for prim in prims:
                        if not prim.metadata_json:
                            continue
                        try:
                            meta = json.loads(prim.metadata_json)
                            val = float(meta.get(measure.metadata_key, 0.0))
                            values.append(val)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            continue

                    cell[measure.metadata_key] = self._python_aggregate(
                        values, measure.aggregation,
                    )
                cells[(row_id, col_id)] = cell

        return cells

    @api.model
    def _get_intersection_primitives(self, row_id, col_id):
        """Return list of primitive element IDs in the intersection of
        row_id and col_id materialized views."""
        Element = self.env['setdb.element']
        row_elem = Element.browse(row_id)
        col_elem = Element.browse(col_id)

        if row_elem.element_type == 'primitive' and col_elem.element_type == 'primitive':
            return [row_id] if row_id == col_id else []

        if row_elem.element_type == 'primitive':
            # Check if row primitive is in col's flatten
            self.env.cr.execute("""
                SELECT 1 FROM setdb_matview_primitive_rel mp
                JOIN setdb_materialized_view mv ON mv.id = mp.matview_id
                WHERE mv.source_id = %s AND mp.element_id = %s
                  AND mv.is_stale = FALSE
                LIMIT 1
            """, (col_id, row_id))
            return [row_id] if self.env.cr.fetchone() else []

        if col_elem.element_type == 'primitive':
            self.env.cr.execute("""
                SELECT 1 FROM setdb_matview_primitive_rel mp
                JOIN setdb_materialized_view mv ON mv.id = mp.matview_id
                WHERE mv.source_id = %s AND mp.element_id = %s
                  AND mv.is_stale = FALSE
                LIMIT 1
            """, (row_id, col_id))
            return [col_id] if self.env.cr.fetchone() else []

        # Both are sets — intersect their materialized views
        self.env.cr.execute("""
            SELECT rp.element_id
            FROM setdb_matview_primitive_rel rp
            JOIN setdb_materialized_view rmv ON rmv.id = rp.matview_id
            JOIN setdb_matview_primitive_rel cp ON cp.element_id = rp.element_id
            JOIN setdb_materialized_view cmv ON cmv.id = cp.matview_id
            WHERE rmv.source_id = %s AND cmv.source_id = %s
              AND rmv.is_stale = FALSE AND cmv.is_stale = FALSE
        """, (row_id, col_id))
        return [r[0] for r in self.env.cr.fetchall()]

    @api.model
    def _python_aggregate(self, values, aggregation):
        """Compute an aggregation in Python."""
        if not values:
            return 0.0
        if aggregation == 'median':
            return statistics.median(values)
        if aggregation == 'variance':
            return statistics.variance(values) if len(values) > 1 else 0.0
        if aggregation == 'stddev':
            return statistics.stdev(values) if len(values) > 1 else 0.0
        # Fallback for any SQL aggregation done in Python
        if aggregation == 'sum':
            return sum(values)
        if aggregation == 'count':
            return float(len(values))
        if aggregation == 'avg':
            return statistics.mean(values)
        if aggregation == 'min':
            return min(values)
        if aggregation == 'max':
            return max(values)
        if aggregation == 'count_distinct':
            return float(len(set(values)))
        return 0.0

    @api.model
    def _aggregate_values(self, values, aggregation):
        """Aggregate a list of pre-computed cell values for totals."""
        if not values:
            return 0.0
        if aggregation in ('sum', 'count', 'count_distinct'):
            return sum(values)
        if aggregation == 'avg':
            return statistics.mean(values)
        if aggregation == 'min':
            return min(values)
        if aggregation == 'max':
            return max(values)
        if aggregation == 'median':
            return statistics.median(values)
        if aggregation == 'variance':
            return statistics.variance(values) if len(values) > 1 else 0.0
        if aggregation == 'stddev':
            return statistics.stdev(values) if len(values) > 1 else 0.0
        return sum(values)
