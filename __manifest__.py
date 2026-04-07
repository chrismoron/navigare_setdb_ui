{
    'name': 'SetDB UI Studio',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'Advanced UI for SetDB: Query Studio, OLAP Cube Explorer, Editor Studio, AI Assistant',
    'description': """
SetDB UI Studio — Advanced Interface for Set-of-Sets Database
=============================================================

Provides a futuristic, feature-rich UI layer on top of the SetDB engine:

**Query Studio** — Full IDE for SetQL queries with syntax highlighting,
autocomplete, saved/parameterized queries, execution history, scheduling,
and visual query builder.

**OLAP Cube Explorer** — Multidimensional spreadsheet inspired by
NAV/Business Central Account Schedules and Analysis Views. Supports
drill-down, roll-up, pivot, slice/dice, formula rows, conditional
formatting, row/column totals, and multiple aggregation types
(sum, count, avg, min, max, variance, stddev).

**Editor Studio** — Visual DAG editor with drag-and-drop, bulk import,
and configurable Odoo Data Bridges for automatic multi-dimension sync.

**Period Engine** — Auto-generates date hierarchies
(Year → Quarter → Month → Week → Day) with σ-algebra partition enforcement.

**Email Integration** — Send SetQL queries via email, receive results
as HTML tables or CSV attachments.

**AI Assistant** — Claude-powered natural language to SetQL translation,
smart materialization suggestions, and auto-tuning.

**Customization** — User profiles, templates, keyboard shortcuts, dashboard.
    """,
    'author': 'Navigare Space Ltd',
    'website': 'https://navigare.space',
    'license': 'LGPL-3',
    'depends': ['setdb', 'mail', 'web', 'base_setup'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/wizard_views.xml',
        'views/clustering_views.xml',
        'views/saved_query_views.xml',
        'views/cube_views.xml',
        'views/period_views.xml',
        'views/bridge_views.xml',
        'views/mail_views.xml',
        'views/profile_views.xml',
        'views/config_views.xml',
        'views/menu.xml',
        'data/cron.xml',
    ],
    'demo': [
        'data/demo.xml',
    ],
    'assets': {
        'web.assets_backend': [
            # CSS
            'setdb_ui/static/src/css/common.css',
            'setdb_ui/static/src/css/query_studio.css',
            'setdb_ui/static/src/css/cube_explorer.css',
            'setdb_ui/static/src/css/editor_studio.css',
            'setdb_ui/static/src/css/ai_assistant.css',
            # Query Studio JS
            'setdb_ui/static/src/js/query_studio/query_studio.js',
            'setdb_ui/static/src/js/query_studio/query_editor.js',
            'setdb_ui/static/src/js/query_studio/query_results.js',
            'setdb_ui/static/src/js/query_studio/explain_viewer.js',
            'setdb_ui/static/src/js/query_studio/query_history.js',
            'setdb_ui/static/src/js/query_studio/query_builder.js',
            # Cube Explorer JS
            'setdb_ui/static/src/js/cube_explorer/cube_explorer.js',
            'setdb_ui/static/src/js/cube_explorer/cube_grid.js',
            'setdb_ui/static/src/js/cube_explorer/dimension_picker.js',
            'setdb_ui/static/src/js/cube_explorer/cube_cell.js',
            'setdb_ui/static/src/js/cube_explorer/cube_toolbar.js',
            'setdb_ui/static/src/js/cube_explorer/measure_picker.js',
            # Editor Studio JS
            'setdb_ui/static/src/js/editor_studio/editor_studio.js',
            'setdb_ui/static/src/js/editor_studio/dag_canvas.js',
            'setdb_ui/static/src/js/editor_studio/bulk_import.js',
            'setdb_ui/static/src/js/editor_studio/bridge_config.js',
            # AI Assistant JS
            'setdb_ui/static/src/js/ai_assistant/assistant.js',
            'setdb_ui/static/src/js/ai_assistant/suggestion.js',
            # Dashboard JS
            'setdb_ui/static/src/js/dashboard/dashboard.js',
            # OWL Templates
            'setdb_ui/static/src/xml/query_studio.xml',
            'setdb_ui/static/src/xml/cube_explorer.xml',
            'setdb_ui/static/src/xml/editor_studio.xml',
            'setdb_ui/static/src/xml/ai_assistant.xml',
            'setdb_ui/static/src/xml/dashboard.xml',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
