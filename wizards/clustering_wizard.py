import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_ALGORITHM_DESCRIPTIONS = {
    'kmeans': 'K-Means partitions data into K clusters by minimising within-cluster variance. '
              'Best for spherical, evenly-sized clusters.',
    'dbscan': 'DBSCAN finds clusters of arbitrary shape based on point density. '
              'Does not require specifying the number of clusters; can detect noise.',
    'hierarchical': 'Agglomerative clustering builds a hierarchy by successively merging '
                    'the closest pair of clusters. Good for understanding data at multiple scales.',
}


class SetDBClusteringWizard(models.TransientModel):
    _name = 'setdb.clustering.wizard'
    _description = 'SetDB Clustering Wizard'

    # ------------------------------------------------------------------
    # Step navigation
    # ------------------------------------------------------------------
    step = fields.Selection([
        ('1_source', 'Source'),
        ('2_algorithm', 'Algorithm'),
        ('3_parameters', 'Parameters'),
        ('4_preview', 'Preview'),
    ], default='1_source', required=True)

    # ------------------------------------------------------------------
    # Step 1: Source
    # ------------------------------------------------------------------
    source_hierarchy_id = fields.Many2one(
        'setdb.hierarchy', string='Source Hierarchy',
    )
    source_element_id = fields.Many2one(
        'setdb.element', string='Source Element',
        help='Optional: cluster only descendants of this element.',
    )
    feature_keys = fields.Char(
        string='Feature Keys',
        help='Comma-separated metadata_json keys to use as features.',
    )
    available_keys = fields.Text(
        string='Available Keys', compute='_compute_available_keys',
    )

    # ------------------------------------------------------------------
    # Step 2: Algorithm
    # ------------------------------------------------------------------
    algorithm = fields.Selection([
        ('kmeans', 'K-Means'),
        ('dbscan', 'DBSCAN'),
        ('hierarchical', 'Hierarchical (Agglomerative)'),
    ], default='kmeans')
    algorithm_description = fields.Text(
        string='Algorithm Description', compute='_compute_algorithm_description',
    )

    # ------------------------------------------------------------------
    # Step 3: Parameters
    # ------------------------------------------------------------------
    # K-Means
    k = fields.Integer(default=3, string='K (Number of Clusters)')
    max_iterations = fields.Integer(default=100)
    random_seed = fields.Integer(default=42)
    # DBSCAN
    epsilon = fields.Float(default=1.0, string='Epsilon')
    min_samples = fields.Integer(default=5, string='Min Samples')
    # Hierarchical
    linkage = fields.Selection([
        ('single', 'Single'),
        ('complete', 'Complete'),
        ('average', 'Average'),
    ], default='average')
    n_clusters = fields.Integer(default=3, string='Number of Clusters')
    # General
    normalize = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    # Step 4: Preview
    # ------------------------------------------------------------------
    config_name = fields.Char(string='Configuration Name')
    element_count = fields.Integer(
        string='Elements to Cluster', compute='_compute_preview',
    )
    feature_count = fields.Integer(
        string='Feature Dimensions', compute='_compute_preview',
    )
    preview_summary = fields.Text(
        string='Preview Summary', compute='_compute_preview',
    )

    # ------------------------------------------------------------------
    # Computed fields
    # ------------------------------------------------------------------

    @api.depends('source_hierarchy_id', 'source_element_id')
    def _compute_available_keys(self):
        for wizard in self:
            keys = set()
            root = wizard.source_element_id or (
                wizard.source_hierarchy_id.root_id if wizard.source_hierarchy_id else False
            )
            if root:
                primitives = root.flatten()
                for elem in primitives[:100]:  # Sample first 100
                    if elem.metadata_json:
                        try:
                            meta = json.loads(elem.metadata_json)
                            if isinstance(meta, dict):
                                keys.update(meta.keys())
                        except (json.JSONDecodeError, TypeError):
                            pass
            wizard.available_keys = ', '.join(sorted(keys)) if keys else 'No keys found'

    @api.depends('algorithm')
    def _compute_algorithm_description(self):
        for wizard in self:
            wizard.algorithm_description = _ALGORITHM_DESCRIPTIONS.get(
                wizard.algorithm, '',
            )

    @api.depends('source_hierarchy_id', 'source_element_id', 'feature_keys')
    def _compute_preview(self):
        for wizard in self:
            root = wizard.source_element_id or (
                wizard.source_hierarchy_id.root_id if wizard.source_hierarchy_id else False
            )
            if root:
                primitives = root.flatten()
                wizard.element_count = len(primitives)
            else:
                wizard.element_count = 0

            keys = [k.strip() for k in (wizard.feature_keys or '').split(',') if k.strip()]
            wizard.feature_count = len(keys)

            lines = []
            lines.append("Configuration: %s" % (wizard.config_name or '(unnamed)'))
            lines.append("Algorithm: %s" % (wizard.algorithm or '-'))
            lines.append("Elements: %d" % wizard.element_count)
            lines.append("Features: %d (%s)" % (wizard.feature_count, wizard.feature_keys or ''))
            if wizard.algorithm == 'kmeans':
                lines.append("K=%d, max_iter=%d, seed=%d" % (
                    wizard.k, wizard.max_iterations, wizard.random_seed,
                ))
            elif wizard.algorithm == 'dbscan':
                lines.append("epsilon=%.2f, min_samples=%d" % (
                    wizard.epsilon, wizard.min_samples,
                ))
            elif wizard.algorithm == 'hierarchical':
                lines.append("n_clusters=%d, linkage=%s" % (
                    wizard.n_clusters, wizard.linkage or 'average',
                ))
            lines.append("Normalize: %s" % ('Yes' if wizard.normalize else 'No'))
            wizard.preview_summary = '\n'.join(lines)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def action_next_step(self):
        self.ensure_one()
        steps = ['1_source', '2_algorithm', '3_parameters', '4_preview']
        idx = steps.index(self.step)
        if self.step == '1_source':
            if not self.source_hierarchy_id:
                raise UserError("Please select a source hierarchy.")
            if not self.feature_keys:
                raise UserError("Please specify at least one feature key.")
        if idx < len(steps) - 1:
            self.step = steps[idx + 1]
        return self._reopen()

    def action_prev_step(self):
        self.ensure_one()
        steps = ['1_source', '2_algorithm', '3_parameters', '4_preview']
        idx = steps.index(self.step)
        if idx > 0:
            self.step = steps[idx - 1]
        return self._reopen()

    def action_run(self):
        """Create a clustering config and run the algorithm."""
        self.ensure_one()
        if not self.config_name:
            raise UserError("Please provide a configuration name.")
        if not self.source_hierarchy_id:
            raise UserError("Please select a source hierarchy.")

        Config = self.env['setdb.clustering.config']
        config = Config.create({
            'name': self.config_name,
            'source_hierarchy_id': self.source_hierarchy_id.id,
            'source_element_id': self.source_element_id.id if self.source_element_id else False,
            'algorithm': self.algorithm,
            'feature_keys': self.feature_keys,
            'k': self.k,
            'max_iterations': self.max_iterations,
            'random_seed': self.random_seed,
            'epsilon': self.epsilon,
            'min_samples': self.min_samples,
            'linkage': self.linkage,
            'n_clusters': self.n_clusters,
            'normalize': self.normalize,
        })
        return config.action_run()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'name': 'Clustering Wizard',
            'res_model': 'setdb.clustering.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
