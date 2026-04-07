import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBClusteringConfig(models.Model):
    _name = 'setdb.clustering.config'
    _description = 'SetDB Clustering Configuration'
    _order = 'name'

    name = fields.Char(required=True, index=True)
    description = fields.Text()
    source_hierarchy_id = fields.Many2one(
        'setdb.hierarchy', required=True, ondelete='restrict',
        string='Source Hierarchy',
    )
    source_element_id = fields.Many2one(
        'setdb.element', string='Source Element',
        help='Optional: cluster only descendants of this element. '
             'If empty, uses the hierarchy root.',
    )
    algorithm = fields.Selection([
        ('kmeans', 'K-Means'),
        ('dbscan', 'DBSCAN'),
        ('hierarchical', 'Hierarchical (Agglomerative)'),
    ], default='kmeans', required=True)
    feature_keys = fields.Char(
        required=True,
        help='Comma-separated metadata_json keys to use as feature dimensions.',
    )

    # K-Means parameters
    k = fields.Integer(default=3, string='K (Number of Clusters)')
    max_iterations = fields.Integer(default=100)
    random_seed = fields.Integer(default=42)

    # DBSCAN parameters
    epsilon = fields.Float(default=1.0, string='Epsilon (Neighbourhood Radius)')
    min_samples = fields.Integer(default=5, string='Min Samples')

    # Hierarchical parameters
    linkage = fields.Selection([
        ('single', 'Single'),
        ('complete', 'Complete'),
        ('average', 'Average'),
    ], default='average')
    n_clusters = fields.Integer(default=3, string='Number of Clusters')

    # General options
    normalize = fields.Boolean(default=True, help='Min-max normalize features to [0, 1].')

    # Results
    result_ids = fields.One2many('setdb.clustering.result', 'config_id', string='Results')
    last_result_id = fields.Many2one(
        'setdb.clustering.result', string='Last Result', readonly=True,
    )

    author_id = fields.Many2one(
        'res.users', default=lambda self: self.env.uid, readonly=True,
    )
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint('UNIQUE(name)', 'Clustering config name must be unique.')

    def action_run(self):
        """Run the clustering algorithm and store results."""
        self.ensure_one()
        engine = self.env['setdb.clustering.engine']
        result = engine.run_clustering(self)
        self.last_result_id = result
        return {
            'type': 'ir.actions.act_window',
            'name': 'Clustering Result',
            'res_model': 'setdb.clustering.result',
            'res_id': result.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_wizard(self):
        """Open the clustering wizard pre-filled with this config."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Clustering Wizard',
            'res_model': 'setdb.clustering.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_source_hierarchy_id': self.source_hierarchy_id.id,
                'default_source_element_id': self.source_element_id.id,
                'default_algorithm': self.algorithm,
                'default_feature_keys': self.feature_keys,
                'default_config_name': self.name,
            },
        }


class SetDBClusteringResult(models.Model):
    _name = 'setdb.clustering.result'
    _description = 'SetDB Clustering Result'
    _order = 'computed_at desc'

    config_id = fields.Many2one(
        'setdb.clustering.config', required=True, ondelete='cascade',
        string='Configuration',
    )
    name = fields.Char(index=True)
    root_element_id = fields.Many2one(
        'setdb.element', string='Root Element', readonly=True,
    )
    hierarchy_id = fields.Many2one(
        'setdb.hierarchy', string='Hierarchy', readonly=True,
    )
    sigma_algebra_id = fields.Many2one(
        'setdb.sigma_algebra', string='Sigma-Algebra', readonly=True,
    )

    n_clusters = fields.Integer(string='Number of Clusters', readonly=True)
    n_elements = fields.Integer(string='Number of Elements', readonly=True)
    n_noise = fields.Integer(string='Noise Points', readonly=True)
    silhouette_score = fields.Float(string='Silhouette Score', readonly=True, digits=(10, 4))
    inertia = fields.Float(string='Inertia', readonly=True, digits=(16, 4))

    centroids_json = fields.Text(string='Centroids (JSON)', readonly=True)
    cluster_sizes_json = fields.Text(string='Cluster Sizes (JSON)', readonly=True)
    diagnostics_json = fields.Text(string='Diagnostics (JSON)', readonly=True)

    computed_at = fields.Datetime(readonly=True)
    duration_seconds = fields.Float(string='Duration (s)', readonly=True, digits=(10, 3))
    active = fields.Boolean(default=True)

    def action_open_in_cube(self):
        """Create or open an OLAP cube using the clustering hierarchy."""
        self.ensure_one()
        if not self.hierarchy_id:
            raise UserError("No hierarchy associated with this result.")
        cube = self.env['setdb.cube'].search([
            ('name', '=', f"Cube: {self.name}"),
        ], limit=1)
        if not cube:
            cube = self.env['setdb.cube'].create({
                'name': f"Cube: {self.name}",
                'description': f"Auto-created cube for clustering result '{self.name}'.",
                'row_hierarchy_id': self.hierarchy_id.id,
                'column_hierarchy_id': self.config_id.source_hierarchy_id.id,
            })
        return {
            'type': 'ir.actions.act_window',
            'name': 'Cube Explorer',
            'res_model': 'setdb.cube',
            'res_id': cube.id,
            'view_mode': 'form',
            'target': 'current',
        }
