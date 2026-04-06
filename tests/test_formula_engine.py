from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError


class TestFormulaEngine(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.engine = cls.env['setdb.formula.engine']

    def test_simple_addition(self):
        """Test row:a + row:b evaluates correctly."""
        result = self.engine.evaluate_formula(
            'row:a + row:b',
            {'a': 10, 'b': 20},
        )
        self.assertAlmostEqual(result, 30.0)

    def test_subtraction(self):
        """Test row:a - row:b."""
        result = self.engine.evaluate_formula(
            'row:a - row:b',
            {'a': 50, 'b': 20},
        )
        self.assertAlmostEqual(result, 30.0)

    def test_mixed_arithmetic(self):
        """Test row:a * 2 - row:b / 4."""
        result = self.engine.evaluate_formula(
            'row:a * 2 - row:b / 4',
            {'a': 10, 'b': 20},
        )
        # 10*2 - 20/4 = 20 - 5 = 15
        self.assertAlmostEqual(result, 15.0)

    def test_parenthesized_expression(self):
        """Test (row:a + row:b) * 0.23."""
        result = self.engine.evaluate_formula(
            '(row:a + row:b) * 0.23',
            {'a': 100, 'b': 200},
        )
        # (100 + 200) * 0.23 = 69.0
        self.assertAlmostEqual(result, 69.0)

    def test_division_by_zero_returns_zero(self):
        """Division by zero should return 0.0 (safety)."""
        result = self.engine.evaluate_formula(
            'row:a / row:b',
            {'a': 100, 'b': 0},
        )
        self.assertAlmostEqual(result, 0.0)

    def test_nested_parentheses(self):
        """Test nested parentheses: ((row:a + row:b) * (row:c - row:d))."""
        result = self.engine.evaluate_formula(
            '((row:a + row:b) * (row:c - row:d))',
            {'a': 5, 'b': 3, 'c': 10, 'd': 4},
        )
        # (5+3) * (10-4) = 8 * 6 = 48
        self.assertAlmostEqual(result, 48.0)

    def test_unary_minus(self):
        """Test unary minus: -row:a + row:b."""
        result = self.engine.evaluate_formula(
            '-row:a + row:b',
            {'a': 10, 'b': 25},
        )
        self.assertAlmostEqual(result, 15.0)

    def test_number_literal_only(self):
        """Test formula with just a number literal."""
        result = self.engine.evaluate_formula(
            '42.5',
            {},
        )
        self.assertAlmostEqual(result, 42.5)

    def test_case_insensitive_row_refs(self):
        """Row references should be case-insensitive."""
        result = self.engine.evaluate_formula(
            'row:MyValue + row:other',
            {'myvalue': 10, 'other': 5},
        )
        self.assertAlmostEqual(result, 15.0)

    def test_undefined_reference_raises_error(self):
        """Referencing an undefined row should raise UserError."""
        with self.assertRaises(UserError):
            self.engine.evaluate_formula(
                'row:nonexistent + row:a',
                {'a': 10},
            )

    def test_empty_formula_returns_zero(self):
        """Empty formula text should return 0.0."""
        result = self.engine.evaluate_formula('', {})
        self.assertAlmostEqual(result, 0.0)

    def test_complex_formula(self):
        """Test a more complex expression with multiple operations."""
        result = self.engine.evaluate_formula(
            '(row:revenue - row:costs) / row:revenue * 100',
            {'revenue': 200, 'costs': 50},
        )
        # (200-50)/200*100 = 150/200*100 = 75.0
        self.assertAlmostEqual(result, 75.0)
