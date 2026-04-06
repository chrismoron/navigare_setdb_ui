import calendar
import json
import logging
from datetime import date, timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBPeriodConfig(models.Model):
    _name = 'setdb.period.config'
    _description = 'SetDB Period Configuration'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    fiscal_year_start_month = fields.Integer(
        default=1,
        help='Month number (1-12) when the fiscal year starts. '
             'E.g. 4 for April.',
    )
    generate_days = fields.Boolean(default=False)
    generate_weeks = fields.Boolean(default=True)
    generate_months = fields.Boolean(default=True)
    generate_quarters = fields.Boolean(default=True)
    year_start = fields.Integer(required=True, default=2024)
    year_end = fields.Integer(required=True, default=2030)
    hierarchy_id = fields.Many2one(
        'setdb.hierarchy', readonly=True,
        string='Generated Hierarchy',
    )
    sigma_algebra_id = fields.Many2one(
        'setdb.sigma_algebra', readonly=True,
        string='Generated Sigma-Algebra',
    )
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @api.constrains('fiscal_year_start_month')
    def _check_fiscal_month(self):
        for rec in self:
            if not (1 <= rec.fiscal_year_start_month <= 12):
                raise UserError('Fiscal year start month must be between 1 and 12.')

    @api.constrains('year_start', 'year_end')
    def _check_year_range(self):
        for rec in self:
            if rec.year_start > rec.year_end:
                raise UserError('Year start must be <= year end.')

    # ------------------------------------------------------------------
    # Fiscal calendar helpers
    # ------------------------------------------------------------------

    def _fiscal_quarter_months(self, quarter_num):
        """Return 3 month numbers for a fiscal quarter (1-based).

        If fiscal_year_start_month = 4:
            Q1 = [4, 5, 6], Q2 = [7, 8, 9], Q3 = [10, 11, 12], Q4 = [1, 2, 3]
        """
        self.ensure_one()
        start = self.fiscal_year_start_month
        offset = (quarter_num - 1) * 3
        return [((start - 1 + offset + i) % 12) + 1 for i in range(3)]

    def _fiscal_year_range(self, cal_year):
        """Return (date_from, date_to) for a fiscal year.

        For a calendar year, the fiscal year may span two calendar years.
        E.g. fiscal_year_start_month=4, cal_year=2024 → 2024-04-01 to 2025-03-31.
        """
        self.ensure_one()
        start_month = self.fiscal_year_start_month
        fy_start = date(cal_year, start_month, 1)
        if start_month == 1:
            fy_end = date(cal_year, 12, 31)
        else:
            end_year = cal_year + 1
            end_month = start_month - 1
            last_day = calendar.monthrange(end_year, end_month)[1]
            fy_end = date(end_year, end_month, last_day)
        return fy_start, fy_end

    def _month_date_range(self, year, month):
        """Return (date_from, date_to) for a given month."""
        first = date(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        last = date(year, month, last_day)
        return first, last

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def action_generate(self):
        """Generate the period hierarchy and sigma-algebra."""
        self.ensure_one()

        Element = self.env['setdb.element']
        Edge = self.env['setdb.edge']

        all_year_elements = []
        all_quarter_elements = []
        all_edges = []

        # Pre-generate for batch creation — collect dicts, then create in bulk.
        # We use a two-pass approach: first create elements, then edges.

        root_name = '%s Periods' % self.name

        # --- Pass 1: create all elements ---
        element_vals = []
        # Index tracking for edge wiring
        # Structure: root -> years -> quarters -> months -> weeks -> days
        # We build a tree of indices into element_vals

        # Root element (index 0)
        element_vals.append({
            'name': root_name,
            'element_type': 'set',
            'metadata_json': json.dumps({
                'period_type': 'root',
                'config_id': self.id,
            }),
        })

        tree = []  # list of {year_idx, quarter_indices: [{q_idx, month_indices: [...]}]}

        idx = 1  # next index in element_vals

        for cal_year in range(self.year_start, self.year_end + 1):
            fy_start, fy_end = self._fiscal_year_range(cal_year)
            year_label = 'FY%d' % cal_year if self.fiscal_year_start_month != 1 else str(cal_year)

            element_vals.append({
                'name': year_label,
                'element_type': 'set',
                'metadata_json': json.dumps({
                    'period_type': 'year',
                    'date_from': fy_start.isoformat(),
                    'date_to': fy_end.isoformat(),
                    'calendar_year': cal_year,
                }),
            })
            year_idx = idx
            idx += 1

            year_node = {'idx': year_idx, 'quarters': []}

            if self.generate_quarters:
                for q_num in range(1, 5):
                    q_months = self._fiscal_quarter_months(q_num)
                    # Determine calendar years for each month
                    q_start_month = q_months[0]
                    q_end_month = q_months[-1]

                    q_start_year = cal_year if q_start_month >= self.fiscal_year_start_month else cal_year + 1
                    q_end_year = cal_year if q_end_month >= self.fiscal_year_start_month else cal_year + 1
                    if self.fiscal_year_start_month == 1:
                        q_start_year = cal_year
                        q_end_year = cal_year

                    q_start_date = date(q_start_year, q_start_month, 1)
                    q_end_last_day = calendar.monthrange(q_end_year, q_end_month)[1]
                    q_end_date = date(q_end_year, q_end_month, q_end_last_day)

                    element_vals.append({
                        'name': '%s Q%d' % (year_label, q_num),
                        'element_type': 'set',
                        'metadata_json': json.dumps({
                            'period_type': 'quarter',
                            'date_from': q_start_date.isoformat(),
                            'date_to': q_end_date.isoformat(),
                            'quarter': q_num,
                        }),
                    })
                    q_idx = idx
                    idx += 1

                    q_node = {'idx': q_idx, 'months': []}

                    if self.generate_months:
                        for m in q_months:
                            m_year = cal_year if m >= self.fiscal_year_start_month else cal_year + 1
                            if self.fiscal_year_start_month == 1:
                                m_year = cal_year
                            m_start, m_end = self._month_date_range(m_year, m)
                            m_label = m_start.strftime('%Y-%m %B')

                            element_vals.append({
                                'name': m_label,
                                'element_type': 'set' if (self.generate_weeks or self.generate_days) else 'primitive',
                                'metadata_json': json.dumps({
                                    'period_type': 'month',
                                    'date_from': m_start.isoformat(),
                                    'date_to': m_end.isoformat(),
                                    'month': m,
                                }),
                            })
                            m_idx = idx
                            idx += 1

                            m_node = {'idx': m_idx, 'weeks': [], 'days': []}

                            if self.generate_weeks:
                                # ISO weeks overlapping this month
                                seen_weeks = set()
                                d = m_start
                                while d <= m_end:
                                    iso_year, iso_week, _ = d.isocalendar()
                                    wk_key = (iso_year, iso_week)
                                    if wk_key not in seen_weeks:
                                        seen_weeks.add(wk_key)
                                        # Week start (Monday) and end (Sunday)
                                        wk_start = d - timedelta(days=d.weekday())
                                        wk_end = wk_start + timedelta(days=6)
                                        # Clamp to month boundaries
                                        wk_start_clamped = max(wk_start, m_start)
                                        wk_end_clamped = min(wk_end, m_end)

                                        element_vals.append({
                                            'name': '%dW%02d' % (iso_year, iso_week),
                                            'element_type': 'set' if self.generate_days else 'primitive',
                                            'metadata_json': json.dumps({
                                                'period_type': 'week',
                                                'date_from': wk_start_clamped.isoformat(),
                                                'date_to': wk_end_clamped.isoformat(),
                                                'iso_week': iso_week,
                                                'iso_year': iso_year,
                                            }),
                                        })
                                        w_idx = idx
                                        idx += 1
                                        w_node = {'idx': w_idx, 'days': []}

                                        if self.generate_days:
                                            # Days within the clamped week
                                            dd = wk_start_clamped
                                            while dd <= wk_end_clamped:
                                                element_vals.append({
                                                    'name': dd.isoformat(),
                                                    'element_type': 'primitive',
                                                    'metadata_json': json.dumps({
                                                        'period_type': 'day',
                                                        'date_from': dd.isoformat(),
                                                        'date_to': dd.isoformat(),
                                                    }),
                                                })
                                                w_node['days'].append(idx)
                                                idx += 1
                                                dd += timedelta(days=1)

                                        m_node['weeks'].append(w_node)
                                    d += timedelta(days=1)

                            elif self.generate_days:
                                # Days directly under months (no weeks)
                                d = m_start
                                while d <= m_end:
                                    element_vals.append({
                                        'name': d.isoformat(),
                                        'element_type': 'primitive',
                                        'metadata_json': json.dumps({
                                            'period_type': 'day',
                                            'date_from': d.isoformat(),
                                            'date_to': d.isoformat(),
                                        }),
                                    })
                                    m_node['days'].append(idx)
                                    idx += 1
                                    d += timedelta(days=1)

                            q_node['months'].append(m_node)

                    year_node['quarters'].append(q_node)

            elif self.generate_months:
                # Months directly under year (no quarters)
                year_node['months'] = []
                for q_num in range(1, 5):
                    q_months = self._fiscal_quarter_months(q_num)
                    for m in q_months:
                        m_year = cal_year if m >= self.fiscal_year_start_month else cal_year + 1
                        if self.fiscal_year_start_month == 1:
                            m_year = cal_year
                        m_start, m_end = self._month_date_range(m_year, m)
                        m_label = m_start.strftime('%Y-%m %B')

                        element_vals.append({
                            'name': m_label,
                            'element_type': 'set' if (self.generate_weeks or self.generate_days) else 'primitive',
                            'metadata_json': json.dumps({
                                'period_type': 'month',
                                'date_from': m_start.isoformat(),
                                'date_to': m_end.isoformat(),
                                'month': m,
                            }),
                        })
                        m_idx = idx
                        idx += 1
                        year_node.setdefault('months', []).append({'idx': m_idx, 'weeks': [], 'days': []})

            tree.append(year_node)

        # Batch create all elements
        _logger.info("Creating %d period elements for config '%s'.", len(element_vals), self.name)
        elements = Element.create(element_vals)

        # --- Pass 2: create edges ---
        edge_vals = []
        root_el = elements[0]

        for year_node in tree:
            year_el = elements[year_node['idx']]
            edge_vals.append({
                'parent_id': root_el.id,
                'child_id': year_el.id,
                'ordinal': len(edge_vals),
            })

            children = year_node.get('quarters', year_node.get('months', []))
            for child_ord, child_node in enumerate(children):
                child_el = elements[child_node['idx']]
                edge_vals.append({
                    'parent_id': year_el.id,
                    'child_id': child_el.id,
                    'ordinal': child_ord,
                })

                # Quarter -> months
                for m_ord, m_node in enumerate(child_node.get('months', [])):
                    m_el = elements[m_node['idx']]
                    edge_vals.append({
                        'parent_id': child_el.id,
                        'child_id': m_el.id,
                        'ordinal': m_ord,
                    })

                    # Month -> weeks
                    for w_ord, w_node in enumerate(m_node.get('weeks', [])):
                        w_el = elements[w_node['idx']]
                        edge_vals.append({
                            'parent_id': m_el.id,
                            'child_id': w_el.id,
                            'ordinal': w_ord,
                        })
                        # Week -> days
                        for d_ord, d_idx in enumerate(w_node.get('days', [])):
                            d_el = elements[d_idx]
                            edge_vals.append({
                                'parent_id': w_el.id,
                                'child_id': d_el.id,
                                'ordinal': d_ord,
                            })

                    # Month -> days (when no weeks)
                    for d_ord, d_idx in enumerate(m_node.get('days', [])):
                        d_el = elements[d_idx]
                        edge_vals.append({
                            'parent_id': m_el.id,
                            'child_id': d_el.id,
                            'ordinal': d_ord,
                        })

                # If months are directly under years (no quarters), handle weeks/days
                if 'months' not in child_node and 'weeks' not in child_node:
                    pass  # leaf node, no further nesting

        _logger.info("Creating %d edges for period config '%s'.", len(edge_vals), self.name)
        Edge.create(edge_vals)

        # --- Create hierarchy ---
        hierarchy = self.env['setdb.hierarchy'].create({
            'name': '%s Hierarchy' % self.name,
            'root_id': root_el.id,
            'hierarchy_type': 'tree',
        })

        # --- Create sigma-algebra with partition enforcement on quarters ---
        quarter_elements = self.env['setdb.element']
        if self.generate_quarters:
            for year_node in tree:
                for q_node in year_node.get('quarters', []):
                    quarter_elements |= elements[q_node['idx']]

        sigma = self.env['setdb.sigma_algebra'].create({
            'name': '%s Sigma-Algebra' % self.name,
            'omega_id': root_el.id,
            'enforce_partition': bool(self.generate_quarters),
            'partition_depth': 2,
            'validate_on_modify': False,
            'member_ids': [fields.Command.set(quarter_elements.ids)] if quarter_elements else [],
        })

        self.write({
            'hierarchy_id': hierarchy.id,
            'sigma_algebra_id': sigma.id,
        })

        _logger.info(
            "Period config '%s' generated: %d elements, hierarchy=%d, sigma_algebra=%d.",
            self.name, len(elements), hierarchy.id, sigma.id,
        )

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Period Generation Complete',
                'message': '%d elements created.' % len(elements),
                'type': 'success',
                'sticky': False,
            },
        }
