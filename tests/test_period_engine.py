import json

from odoo.tests.common import TransactionCase


class TestPeriodEngine(TransactionCase):

    def test_generate_period_creates_hierarchy(self):
        """Creating a period config and generating should produce a hierarchy."""
        config = self.env['setdb.period.config'].create({
            'name': 'Test Period 2025',
            'fiscal_year_start_month': 1,
            'year_start': 2025,
            'year_end': 2025,
            'generate_months': True,
            'generate_quarters': True,
            'generate_weeks': False,
            'generate_days': False,
        })
        self.assertFalse(config.hierarchy_id)

        config.action_generate()

        self.assertTrue(config.hierarchy_id, "Hierarchy should be created after generation")
        self.assertEqual(config.hierarchy_id.hierarchy_type, 'tree')
        self.assertTrue(config.hierarchy_id.root_id, "Hierarchy should have a root element")

    def test_generate_creates_correct_element_count(self):
        """For 1 year with quarters and months: root + 1 year + 4 quarters + 12 months = 18."""
        config = self.env['setdb.period.config'].create({
            'name': 'Test Period Count',
            'fiscal_year_start_month': 1,
            'year_start': 2025,
            'year_end': 2025,
            'generate_months': True,
            'generate_quarters': True,
            'generate_weeks': False,
            'generate_days': False,
        })
        config.action_generate()

        root = config.hierarchy_id.root_id
        # Root should have 1 year child
        year_elements = root.members()
        self.assertEqual(len(year_elements), 1, "Root should have exactly 1 year element")
        year = year_elements[0]
        self.assertIn('2025', year.name)

        # Year should have 4 quarter children
        quarters = year.members()
        self.assertEqual(len(quarters), 4, "Year should have 4 quarters")

        # Each quarter should have 3 month children
        total_months = 0
        for q in quarters:
            months = q.members()
            self.assertEqual(len(months), 3, "Each quarter should have 3 months")
            total_months += len(months)
        self.assertEqual(total_months, 12)

    def test_month_elements_have_correct_metadata(self):
        """Month elements should have period_type=month and valid date_from/date_to."""
        config = self.env['setdb.period.config'].create({
            'name': 'Test Month Metadata',
            'fiscal_year_start_month': 1,
            'year_start': 2025,
            'year_end': 2025,
            'generate_months': True,
            'generate_quarters': True,
            'generate_weeks': False,
            'generate_days': False,
        })
        config.action_generate()

        root = config.hierarchy_id.root_id
        year = root.members()[0]
        q1 = year.members()[0]
        jan = q1.members()[0]

        meta = json.loads(jan.metadata_json)
        self.assertEqual(meta['period_type'], 'month')
        self.assertEqual(meta['date_from'], '2025-01-01')
        self.assertEqual(meta['date_to'], '2025-01-31')

    def test_sigma_algebra_created(self):
        """Generation should create a sigma-algebra associated with the config."""
        config = self.env['setdb.period.config'].create({
            'name': 'Test Sigma Period',
            'fiscal_year_start_month': 1,
            'year_start': 2025,
            'year_end': 2025,
            'generate_months': True,
            'generate_quarters': True,
            'generate_weeks': False,
            'generate_days': False,
        })
        config.action_generate()

        self.assertTrue(config.sigma_algebra_id, "Sigma-algebra should be created")
        self.assertTrue(config.sigma_algebra_id.omega_id, "Sigma-algebra should have omega")
        self.assertEqual(
            config.sigma_algebra_id.omega_id.id,
            config.hierarchy_id.root_id.id,
            "Sigma-algebra omega should be the period root",
        )

    def test_sigma_algebra_partition_members(self):
        """When quarters are generated, sigma-algebra members should include quarters."""
        config = self.env['setdb.period.config'].create({
            'name': 'Test Partition Members',
            'fiscal_year_start_month': 1,
            'year_start': 2025,
            'year_end': 2025,
            'generate_months': True,
            'generate_quarters': True,
            'generate_weeks': False,
            'generate_days': False,
        })
        config.action_generate()

        sigma = config.sigma_algebra_id
        self.assertTrue(sigma.enforce_partition)
        # Members should contain the 4 quarter elements
        member_names = sigma.member_ids.mapped('name')
        self.assertEqual(len(sigma.member_ids), 4, "Sigma members should be 4 quarters")
        for q_num in range(1, 5):
            q_name = '2025 Q%d' % q_num
            self.assertIn(q_name, member_names, "Quarter %s should be a sigma member" % q_name)

    def test_multi_year_generation(self):
        """Generating across 2 years should create 2 year elements."""
        config = self.env['setdb.period.config'].create({
            'name': 'Test Multi Year',
            'fiscal_year_start_month': 1,
            'year_start': 2025,
            'year_end': 2026,
            'generate_months': True,
            'generate_quarters': True,
            'generate_weeks': False,
            'generate_days': False,
        })
        config.action_generate()

        root = config.hierarchy_id.root_id
        years = root.members()
        self.assertEqual(len(years), 2)
        year_names = years.mapped('name')
        self.assertIn('2025', year_names)
        self.assertIn('2026', year_names)

    def test_months_are_primitives_when_no_weeks_or_days(self):
        """When weeks and days are disabled, month elements should be primitives."""
        config = self.env['setdb.period.config'].create({
            'name': 'Test Month Primitives',
            'fiscal_year_start_month': 1,
            'year_start': 2025,
            'year_end': 2025,
            'generate_months': True,
            'generate_quarters': True,
            'generate_weeks': False,
            'generate_days': False,
        })
        config.action_generate()

        root = config.hierarchy_id.root_id
        year = root.members()[0]
        q1 = year.members()[0]
        months = q1.members()
        for m in months:
            self.assertEqual(m.element_type, 'primitive',
                             "Month '%s' should be primitive when weeks/days are disabled" % m.name)
