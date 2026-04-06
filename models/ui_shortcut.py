from odoo import fields, models


class SetDBUIShortcut(models.Model):
    _name = 'setdb.ui.shortcut'
    _description = 'SetDB UI Shortcut'
    _order = 'sequence, id'

    user_id = fields.Many2one(
        'res.users', required=True,
        default=lambda self: self.env.uid,
        ondelete='cascade',
    )
    name = fields.Char(required=True)
    action_type = fields.Selection([
        ('query', 'Saved Query'),
        ('cube', 'Cube'),
        ('report', 'Report'),
    ], required=True)
    target_id = fields.Integer(help='ID of the target saved_query or cube')
    keyboard_shortcut = fields.Char(help='e.g., Ctrl+Shift+1')
    sequence = fields.Integer(default=10)
    icon = fields.Char(default='fa-star')

    def action_execute(self):
        """Open the linked target in the appropriate view."""
        self.ensure_one()

        if self.action_type == 'query' and self.target_id:
            query = self.env['setdb.saved.query'].browse(self.target_id)
            if query.exists():
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Query Studio: %s' % query.name,
                    'res_model': 'setdb.saved.query',
                    'res_id': query.id,
                    'view_mode': 'form',
                    'target': 'current',
                }

        elif self.action_type == 'cube' and self.target_id:
            cube = self.env['setdb.cube'].browse(self.target_id)
            if cube.exists():
                return {
                    'type': 'ir.actions.act_window',
                    'name': 'Cube Explorer: %s' % cube.name,
                    'res_model': 'setdb.cube',
                    'res_id': cube.id,
                    'view_mode': 'form',
                    'target': 'current',
                }

        elif self.action_type == 'report' and self.target_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Report',
                'res_model': 'setdb.saved.query',
                'res_id': self.target_id,
                'view_mode': 'form',
                'target': 'current',
            }

        return {'type': 'ir.actions.act_window_close'}
