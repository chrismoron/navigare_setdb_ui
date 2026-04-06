from odoo import fields, models


class SetDBAIConfig(models.TransientModel):
    _inherit = 'res.config.settings'

    setdb_ai_api_key = fields.Char(
        string='AI API Key',
        config_parameter='setdb_ui.ai_api_key',
    )
    setdb_ai_model = fields.Char(
        string='AI Model',
        default='claude-sonnet-4-20250514',
        config_parameter='setdb_ui.ai_model',
    )
    setdb_ai_max_tokens = fields.Integer(
        string='AI Max Tokens',
        default=4096,
        config_parameter='setdb_ui.ai_max_tokens',
    )
    setdb_ai_auto_materialize = fields.Boolean(
        string='AI Auto-Materialize',
        default=False,
        config_parameter='setdb_ui.ai_auto_materialize',
    )
