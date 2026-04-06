import calendar
import logging
from datetime import date

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBPeriodWizard(models.TransientModel):
    _name = 'setdb.period.wizard'
    _description = 'SetDB Period Generation Wizard'

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------
    step = fields.Selection([
        ('1_basics', 'Basics'),
        ('2_granularity', 'Granularity'),
        ('3_preview', 'Preview'),
        ('4_generate', 'Generate'),
    ], default='1_basics', required=True)

    # ------------------------------------------------------------------
    # Step 1: Basics
    # ------------------------------------------------------------------
    name = fields.Char(string='Configuration Name', default='Fiscal Periods', required=True)
    fiscal_year_start_month = fields.Integer(
        string='Fiscal Year Start Month', default=1,
        help='Month number (1-12) when the fiscal year starts.',
    )
    year_start = fields.Integer(string='Start Year', required=True, default=2024)
    year_end = fields.Integer(string='End Year', required=True, default=2026)

    # ------------------------------------------------------------------
    # Step 2: Granularity
    # ------------------------------------------------------------------
    generate_days = fields.Boolean(string='Generate Days', default=False)
    generate_weeks = fields.Boolean(string='Generate Weeks', default=True)
    generate_months = fields.Boolean(string='Generate Months', default=True)
    generate_quarters = fields.Boolean(string='Generate Quarters', default=True)

    # ------------------------------------------------------------------
    # Step 3: Preview
    # ------------------------------------------------------------------
    preview_text = fields.Text(
        string='Hierarchy Preview', readonly=True,
        compute='_compute_preview',
    )
    element_count_estimate = fields.Integer(
        string='Estimated Element Count', readonly=True,
        compute='_compute_element_count',
    )

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    @api.constrains('fiscal_year_start_month')
    def _check_fiscal_month(self):
        for rec in self:
            if rec.fiscal_year_start_month and not (1 <= rec.fiscal_year_start_month <= 12):
                raise UserError('Fiscal year start month must be between 1 and 12.')

    @api.constrains('year_start', 'year_end')
    def _check_year_range(self):
        for rec in self:
            if rec.year_start and rec.year_end and rec.year_start > rec.year_end:
                raise UserError('Start year must be less than or equal to end year.')

    # ------------------------------------------------------------------
    # Fiscal calendar helpers
    # ------------------------------------------------------------------
    def _fiscal_quarter_months(self, quarter_num):
        """Return 3 month numbers for a fiscal quarter."""
        self.ensure_one()
        start = self.fiscal_year_start_month or 1
        offset = (quarter_num - 1) * 3
        return [((start - 1 + offset + i) % 12) + 1 for i in range(3)]

    def _month_label(self, year, month):
        """Return a display label for a month."""
        return date(year, month, 1).strftime('%Y-%m %B')

    def _year_label(self, cal_year):
        """Return a display label for a year."""
        if (self.fiscal_year_start_month or 1) != 1:
            return 'FY%d' % cal_year
        return str(cal_year)

    # ------------------------------------------------------------------
    # Compute: preview
    # ------------------------------------------------------------------
    @api.depends(
        'name', 'fiscal_year_start_month', 'year_start', 'year_end',
        'generate_days', 'generate_weeks', 'generate_months', 'generate_quarters',
    )
    def _compute_preview(self):
        for wiz in self:
            wiz.preview_text = wiz._build_preview_text()

    def _build_preview_text(self):
        """Generate a text tree preview of the period hierarchy."""
        self.ensure_one()
        if not self.year_start or not self.year_end:
            return '(configure year range first)'

        lines = []
        root_name = '%s Periods' % (self.name or 'Fiscal')
        lines.append(root_name)

        fy_start = self.fiscal_year_start_month or 1
        max_years_preview = min(self.year_end - self.year_start + 1, 3)
        total_years = self.year_end - self.year_start + 1

        for yr_idx, cal_year in enumerate(range(self.year_start, self.year_start + max_years_preview)):
            year_label = self._year_label(cal_year)
            is_last_year = (yr_idx == max_years_preview - 1)
            y_prefix = '  +-- ' if not is_last_year else '  \\-- '
            y_cont = '  |   ' if not is_last_year else '      '
            lines.append('%s%s' % (y_prefix, year_label))

            if self.generate_quarters:
                for q_num in range(1, 5):
                    is_last_q = (q_num == 4)
                    q_prefix = '%s+-- ' % y_cont if not is_last_q else '%s\\-- ' % y_cont
                    q_cont = '%s|   ' % y_cont if not is_last_q else '%s    ' % y_cont
                    lines.append('%sQ%d' % (q_prefix, q_num))

                    if self.generate_months:
                        q_months = self._fiscal_quarter_months(q_num)
                        for m_idx, m in enumerate(q_months):
                            m_year = cal_year if m >= fy_start else cal_year + 1
                            if fy_start == 1:
                                m_year = cal_year
                            m_label = self._month_label(m_year, m)
                            is_last_m = (m_idx == 2)
                            m_prefix = '%s+-- ' % q_cont if not is_last_m else '%s\\-- ' % q_cont

                            if self.generate_weeks or self.generate_days:
                                lines.append('%s%s (...)' % (m_prefix, m_label))
                            else:
                                lines.append('%s%s' % (m_prefix, m_label))

            elif self.generate_months:
                for q_num in range(1, 5):
                    q_months = self._fiscal_quarter_months(q_num)
                    for m_idx, m in enumerate(q_months):
                        m_year = cal_year if m >= fy_start else cal_year + 1
                        if fy_start == 1:
                            m_year = cal_year
                        m_label = self._month_label(m_year, m)
                        is_last = (q_num == 4 and m_idx == 2)
                        m_prefix = '%s+-- ' % y_cont if not is_last else '%s\\-- ' % y_cont
                        lines.append('%s%s' % (m_prefix, m_label))

        if total_years > max_years_preview:
            lines.append('  ... (%d more years)' % (total_years - max_years_preview))

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Compute: element count estimate
    # ------------------------------------------------------------------
    @api.depends(
        'year_start', 'year_end',
        'generate_days', 'generate_weeks', 'generate_months', 'generate_quarters',
    )
    def _compute_element_count(self):
        for wiz in self:
            wiz.element_count_estimate = wiz._estimate_element_count()

    def _estimate_element_count(self):
        """Estimate how many elements will be created."""
        self.ensure_one()
        if not self.year_start or not self.year_end:
            return 0

        num_years = self.year_end - self.year_start + 1
        count = 1  # root

        for cal_year in range(self.year_start, self.year_end + 1):
            count += 1  # year element

            if self.generate_quarters:
                count += 4  # quarter elements

            months = 12
            if self.generate_months:
                count += months

            if self.generate_weeks:
                # Approximate: ~4.3 weeks per month
                count += int(months * 4.3)

            if self.generate_days:
                # Approximate: 365 or 366 days per year
                is_leap = calendar.isleap(cal_year)
                count += 366 if is_leap else 365

        return count

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def action_next_step(self):
        self.ensure_one()
        step_order = ['1_basics', '2_granularity', '3_preview', '4_generate']
        current_idx = step_order.index(self.step)
        if current_idx < len(step_order) - 1:
            self.step = step_order[current_idx + 1]
        return self._reopen()

    def action_prev_step(self):
        self.ensure_one()
        step_order = ['1_basics', '2_granularity', '3_preview', '4_generate']
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
    # Generate
    # ------------------------------------------------------------------
    def action_generate(self):
        """Create a setdb.period.config and trigger its action_generate()."""
        self.ensure_one()

        if not self.name:
            raise UserError('Please provide a configuration name.')
        if not self.year_start or not self.year_end:
            raise UserError('Please specify a year range.')
        if self.year_start > self.year_end:
            raise UserError('Start year must be less than or equal to end year.')

        config = self.env['setdb.period.config'].create({
            'name': self.name,
            'fiscal_year_start_month': self.fiscal_year_start_month or 1,
            'year_start': self.year_start,
            'year_end': self.year_end,
            'generate_days': self.generate_days,
            'generate_weeks': self.generate_weeks,
            'generate_months': self.generate_months,
            'generate_quarters': self.generate_quarters,
        })

        _logger.info(
            'Period config "%s" created via wizard (id=%d, %d-%d, est. %d elements).',
            config.name, config.id, self.year_start, self.year_end,
            self.element_count_estimate,
        )

        # Trigger the actual generation
        result = config.action_generate()

        # If the period config returns a notification, enhance it
        if isinstance(result, dict) and result.get('tag') == 'display_notification':
            return result

        # Otherwise show the created config
        return {
            'type': 'ir.actions.act_window',
            'name': 'Period Configuration',
            'res_model': 'setdb.period.config',
            'res_id': config.id,
            'view_mode': 'form',
            'target': 'current',
        }
