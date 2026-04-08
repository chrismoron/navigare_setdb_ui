from odoo.tests.common import TransactionCase


class TestSavedQuery(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Create a minimal hierarchy for query execution:
        # root_set -> {prim_a, prim_b}
        Element = cls.env['setdb.element']
        Edge = cls.env['setdb.edge']

        cls.prim_a = Element.create({
            'name': 'sq_prim_a',
            'element_type': 'primitive',
            'metadata_json': '{"value": 10}',
        })
        cls.prim_b = Element.create({
            'name': 'sq_prim_b',
            'element_type': 'primitive',
            'metadata_json': '{"value": 20}',
        })
        cls.root_set = Element.create({
            'name': 'sq_root',
            'element_type': 'set',
        })
        Edge.create({'parent_id': cls.root_set.id, 'child_id': cls.prim_a.id, 'ordinal': 0})
        Edge.create({'parent_id': cls.root_set.id, 'child_id': cls.prim_b.id, 'ordinal': 1})

    def test_create_and_execute_saved_query(self):
        """Create a saved query, execute it, and verify results."""
        query = self.env['setdb.saved.query'].create({
            'name': 'Test Flatten SQ Root',
            'query_text': 'FLATTEN sq_root',
        })
        self.assertEqual(query.execution_count, 0)
        self.assertFalse(query.last_executed)

        result = query.execute_query()
        # FLATTEN should return the two primitives
        self.assertTrue(len(result) >= 2)
        result_names = result.mapped('name')
        self.assertIn('sq_prim_a', result_names)
        self.assertIn('sq_prim_b', result_names)

    def test_execution_logs_history(self):
        """Executing a saved query should create a history record."""
        query = self.env['setdb.saved.query'].create({
            'name': 'Test History Logging',
            'query_text': 'FLATTEN sq_root',
        })
        history_before = self.env['setdb.query.history'].search_count([
            ('saved_query_id', '=', query.id),
        ])
        self.assertEqual(history_before, 0)

        query.execute_query()

        history_after = self.env['setdb.query.history'].search([
            ('saved_query_id', '=', query.id),
        ])
        self.assertEqual(len(history_after), 1)
        self.assertEqual(history_after.status, 'success')
        self.assertTrue(history_after.execution_time_ms >= 0)
        self.assertTrue(history_after.result_count >= 2)

    def test_execution_updates_stats(self):
        """Executing a saved query should update execution_count and avg_execution_time_ms."""
        query = self.env['setdb.saved.query'].create({
            'name': 'Test Stats Update',
            'query_text': 'FLATTEN sq_root',
        })

        query.execute_query()
        self.assertEqual(query.execution_count, 1)
        self.assertTrue(query.avg_execution_time_ms >= 0)
        self.assertTrue(query.last_executed)

        first_avg = query.avg_execution_time_ms

        query.execute_query()
        self.assertEqual(query.execution_count, 2)
        # avg should still be a valid number
        self.assertTrue(query.avg_execution_time_ms >= 0)

    def test_error_query_logs_error_history(self):
        """Executing an invalid query should log an error history entry."""
        query = self.env['setdb.saved.query'].create({
            'name': 'Test Error Query',
            'query_text': 'INVALID_SYNTAX !@#$',
        })
        # Use manual try/except instead of assertRaises to avoid
        # Odoo's savepoint rollback which would undo the error history record.
        raised = False
        try:
            query.execute_query()
        except Exception:
            raised = True

        self.assertTrue(raised, 'Expected an exception from invalid query')
        history = self.env['setdb.query.history'].search([
            ('saved_query_id', '=', query.id),
        ])
        self.assertEqual(len(history), 1)
        self.assertEqual(history.status, 'error')
        self.assertTrue(history.error_message)

    def test_parameterized_query(self):
        """Test parameter substitution in saved queries."""
        query = self.env['setdb.saved.query'].create({
            'name': 'Parameterized Flatten',
            'query_text': 'FLATTEN ${target}',
            'parameters_json': '[{"name": "target", "type": "text", "default": "sq_root"}]',
        })
        result = query.execute_query(parameters={'target': 'sq_root'})
        self.assertTrue(len(result) >= 2)
