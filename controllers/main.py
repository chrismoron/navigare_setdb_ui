import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class SetDBUIController(http.Controller):

    # ------------------------------------------------------------------
    # Query endpoints
    # ------------------------------------------------------------------

    @http.route('/setdb_ui/query/execute', type='jsonrpc', auth='user')
    def query_execute(self, query_id=None, query_text=None, parameters=None):
        """Execute a saved query or ad-hoc query text with history logging.

        Args:
            query_id: int — ID of a setdb.saved.query record (optional)
            query_text: str — raw SetQL text (used when query_id is not given)
            parameters: dict — parameter substitution values (optional)

        Returns:
            dict with keys: result_ids, result_count, execution_time_ms
        """
        import time
        t0 = time.monotonic()

        if query_id:
            saved = request.env['setdb.saved.query'].browse(query_id)
            if not saved.exists():
                return {'error': 'Saved query not found.'}
            result = saved.execute_query(parameters=parameters)
        elif query_text:
            executor = request.env['setdb.query.executor']
            result = executor.execute(query_text)
            elapsed = (time.monotonic() - t0) * 1000
            # Log ad-hoc query history
            request.env['setdb.query.history'].create({
                'query_text': query_text,
                'user_id': request.env.uid,
                'execution_time_ms': elapsed,
                'result_count': len(result) if hasattr(result, '__len__') else 0,
                'status': 'success',
                'parameters_json': json.dumps(parameters) if parameters else False,
            })
        else:
            return {'error': 'Provide query_id or query_text.'}

        elapsed = (time.monotonic() - t0) * 1000
        result_ids = result.ids if hasattr(result, 'ids') else []
        return {
            'result_ids': result_ids,
            'result_count': len(result_ids),
            'execution_time_ms': round(elapsed, 2),
        }

    @http.route('/setdb_ui/query/autocomplete', type='jsonrpc', auth='user')
    def query_autocomplete(self, prefix='', limit=20):
        """Return matching element names for autocompletion.

        Args:
            prefix: str — text prefix to match
            limit: int — max results

        Returns:
            list of dicts: [{name, id, element_type}, ...]
        """
        elements = request.env['setdb.element'].search(
            [('name', 'ilike', prefix)],
            limit=limit,
            order='name',
        )
        return [
            {'id': el.id, 'name': el.name, 'element_type': el.element_type}
            for el in elements
        ]

    @http.route('/setdb_ui/query/keywords', type='jsonrpc', auth='user')
    def query_keywords(self):
        """Return the list of SetQL keywords for syntax highlighting.

        Returns:
            list of str
        """
        keywords = [
            'SELECT', 'FROM', 'WHERE', 'UNION', 'INTERSECT', 'DIFFERENCE',
            'COMPLEMENT', 'POWERSET', 'FLATTEN', 'MEMBERS', 'CHILDREN',
            'ANCESTORS', 'DESCENDANTS', 'FILTER', 'LIMIT', 'ORDER',
            'BY', 'ASC', 'DESC', 'AS', 'IN', 'NOT', 'AND', 'OR',
            'EXISTS', 'CONTAINS', 'SUBSET', 'SUPERSET', 'EQUALS',
            'DEPTH', 'CARDINALITY', 'METADATA', 'TYPE', 'SET',
            'PRIMITIVE', 'SEQUENCE', 'HIERARCHY', 'SIGMA', 'ALGEBRA',
        ]
        return keywords

    # ------------------------------------------------------------------
    # Cube endpoints
    # ------------------------------------------------------------------

    @http.route('/setdb_ui/cube/grid', type='jsonrpc', auth='user')
    def cube_grid(self, cube_id):
        """Compute the full OLAP grid for a cube.

        Args:
            cube_id: int — ID of a setdb.cube record

        Returns:
            dict: grid data (rows, columns, measures, cells, totals, formulas)
        """
        cube = request.env['setdb.cube'].browse(cube_id)
        if not cube.exists():
            return {'error': 'Cube not found.'}
        return cube.compute_grid()

    @http.route('/setdb_ui/cube/drill', type='jsonrpc', auth='user')
    def cube_drill(self, cube_id, axis, element_id, direction='down'):
        """Drill down or up on a cube axis.

        Args:
            cube_id: int
            axis: str — 'row' or 'column'
            element_id: int — element to expand/collapse
            direction: str — 'down' or 'up'

        Returns:
            dict: updated grid data
        """
        cube = request.env['setdb.cube'].browse(cube_id)
        if not cube.exists():
            return {'error': 'Cube not found.'}
        if direction == 'down':
            return cube.drill_down(axis, element_id)
        else:
            return cube.roll_up(axis, element_id)

    @http.route('/setdb_ui/cube/pivot', type='jsonrpc', auth='user')
    def cube_pivot(self, cube_id):
        """Swap rows and columns of a cube.

        Args:
            cube_id: int

        Returns:
            dict: updated grid data
        """
        cube = request.env['setdb.cube'].browse(cube_id)
        if not cube.exists():
            return {'error': 'Cube not found.'}
        return cube.pivot()

    # ------------------------------------------------------------------
    # AI endpoint
    # ------------------------------------------------------------------

    @http.route('/setdb_ui/ai/chat', type='jsonrpc', auth='user')
    def ai_chat(self, message, session_id=None, context=None):
        """Send a message to the AI assistant.

        Args:
            message: str — user message
            session_id: int — existing session ID (optional)
            context: dict — additional context (optional)

        Returns:
            dict: {response, session_id, suggestions}
        """
        AiSession = request.env['setdb.ai.session']

        if session_id:
            session = AiSession.browse(session_id)
            if not session.exists():
                return {'error': 'Session not found.'}
        else:
            session = AiSession.create({
                'user_id': request.env.uid,
            })

        # Delegate to AI engine
        try:
            result = session.send_message(message, context=context)
        except Exception as e:
            _logger.exception('AI chat error')
            return {
                'error': str(e),
                'session_id': session.id,
            }

        return {
            'response': result.content or '',
            'session_id': session.id,
            'suggestions': [result.suggested_query] if result.suggested_query else [],
        }

    # ------------------------------------------------------------------
    # Bridge endpoint
    # ------------------------------------------------------------------

    @http.route('/setdb_ui/bridge/sync', type='jsonrpc', auth='user')
    def bridge_sync(self, bridge_id):
        """Trigger a data bridge synchronization.

        Args:
            bridge_id: int — ID of a setdb.data.bridge record

        Returns:
            dict: sync statistics {created, updated, skipped}
        """
        bridge = request.env['setdb.data.bridge'].browse(bridge_id)
        if not bridge.exists():
            return {'error': 'Bridge not found.'}

        engine = request.env['setdb.bridge.engine']
        stats = engine.sync_bridge(bridge)
        bridge.write({
            'last_sync': request.env['setdb.data.bridge']._fields['last_sync'].today(),
            'last_sync_count': stats.get('created', 0) + stats.get('updated', 0),
        })
        return stats
