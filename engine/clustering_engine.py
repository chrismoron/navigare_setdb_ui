import json
import logging
import math
import random
import time

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SetDBClusteringEngine(models.AbstractModel):
    _name = 'setdb.clustering.engine'
    _description = 'SetDB Clustering Engine (Pure Python)'

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @api.model
    def run_clustering(self, config):
        """Main entry point: extract features, run algorithm, store results.

        Args:
            config: setdb.clustering.config record

        Returns:
            setdb.clustering.result record
        """
        t0 = time.time()

        element_ids, vectors, keys = self._extract_features(config)
        if not vectors:
            raise UserError(
                "No elements with valid numeric features found. "
                "Check that the source hierarchy contains elements with "
                "metadata_json keys: %s" % config.feature_keys
            )

        if config.normalize:
            vectors = self._normalize_vectors(vectors)

        algo = config.algorithm
        if algo == 'kmeans':
            algo_result = self._kmeans(
                vectors, config.k, config.max_iterations, config.random_seed,
            )
        elif algo == 'dbscan':
            algo_result = self._dbscan(vectors, config.epsilon, config.min_samples)
        elif algo == 'hierarchical':
            algo_result = self._hierarchical(vectors, config.n_clusters, config.linkage)
        else:
            raise UserError("Unknown algorithm: %s" % algo)

        labels = algo_result['labels']

        # Compute silhouette score if more than one cluster
        unique_labels = set(labels)
        real_labels = unique_labels - {-1}
        silhouette = 0.0
        if len(real_labels) > 1:
            silhouette = self._silhouette_score(vectors, labels)

        algo_result['silhouette_score'] = silhouette
        duration = time.time() - t0

        result = self._store_results(config, element_ids, labels, algo_result, duration)
        return result

    # ------------------------------------------------------------------
    # Feature Extraction
    # ------------------------------------------------------------------

    @api.model
    def _extract_features(self, config):
        """Read elements from the source hierarchy, parse metadata_json.

        Returns:
            (element_ids, vectors, keys) where
            - element_ids: list of int
            - vectors: list of list of float
            - keys: list of str
        """
        root = config.source_element_id or config.source_hierarchy_id.root_id
        if not root:
            raise UserError("No root element found for the source hierarchy.")

        primitives = root.flatten()
        if not primitives:
            return [], [], []

        keys = [k.strip() for k in config.feature_keys.split(',') if k.strip()]
        if not keys:
            raise UserError("No feature keys specified.")

        element_ids = []
        vectors = []
        for elem in primitives:
            meta = {}
            if elem.metadata_json:
                try:
                    meta = json.loads(elem.metadata_json)
                except (json.JSONDecodeError, TypeError):
                    continue
            vec = []
            valid = True
            for key in keys:
                val = meta.get(key)
                if val is None:
                    valid = False
                    break
                try:
                    vec.append(float(val))
                except (ValueError, TypeError):
                    valid = False
                    break
            if valid and vec:
                element_ids.append(elem.id)
                vectors.append(vec)

        return element_ids, vectors, keys

    # ------------------------------------------------------------------
    # Normalization
    # ------------------------------------------------------------------

    @api.model
    def _normalize_vectors(self, vectors):
        """Min-max normalize each feature dimension to [0, 1]."""
        if not vectors:
            return vectors
        n_features = len(vectors[0])
        mins = [float('inf')] * n_features
        maxs = [float('-inf')] * n_features
        for vec in vectors:
            for i in range(n_features):
                if vec[i] < mins[i]:
                    mins[i] = vec[i]
                if vec[i] > maxs[i]:
                    maxs[i] = vec[i]
        result = []
        for vec in vectors:
            normalized = []
            for i in range(n_features):
                rng = maxs[i] - mins[i]
                if rng == 0:
                    normalized.append(0.0)
                else:
                    normalized.append((vec[i] - mins[i]) / rng)
            result.append(normalized)
        return result

    # ------------------------------------------------------------------
    # Distance
    # ------------------------------------------------------------------

    @api.model
    def _euclidean_distance(self, a, b):
        """Compute Euclidean distance between two vectors."""
        return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))

    # ------------------------------------------------------------------
    # K-Means
    # ------------------------------------------------------------------

    @api.model
    def _kmeans(self, vectors, k, max_iter, seed):
        """K-Means++ initialization + Lloyd's iteration.

        Returns:
            dict with keys: labels, centroids, inertia, iterations
        """
        n = len(vectors)
        if k <= 0:
            raise UserError("K must be a positive integer.")
        if k > n:
            k = n

        rng = random.Random(seed)
        dim = len(vectors[0])

        # K-Means++ initialization
        centroids = [vectors[rng.randint(0, n - 1)][:]]
        for _ in range(1, k):
            distances = []
            for vec in vectors:
                min_dist = min(self._euclidean_distance(vec, c) ** 2 for c in centroids)
                distances.append(min_dist)
            total = sum(distances)
            if total == 0:
                centroids.append(vectors[rng.randint(0, n - 1)][:])
                continue
            threshold = rng.random() * total
            cumulative = 0.0
            for idx, d in enumerate(distances):
                cumulative += d
                if cumulative >= threshold:
                    centroids.append(vectors[idx][:])
                    break
            else:
                centroids.append(vectors[-1][:])

        # Lloyd's iteration
        labels = [0] * n
        iterations = 0
        for iteration in range(max_iter):
            iterations = iteration + 1
            # Assignment step
            changed = False
            for i, vec in enumerate(vectors):
                best_k = 0
                best_dist = float('inf')
                for ki in range(k):
                    d = self._euclidean_distance(vec, centroids[ki])
                    if d < best_dist:
                        best_dist = d
                        best_k = ki
                if labels[i] != best_k:
                    labels[i] = best_k
                    changed = True

            if not changed:
                break

            # Update step
            new_centroids = [[0.0] * dim for _ in range(k)]
            counts = [0] * k
            for i, vec in enumerate(vectors):
                ci = labels[i]
                counts[ci] += 1
                for d in range(dim):
                    new_centroids[ci][d] += vec[d]
            for ki in range(k):
                if counts[ki] > 0:
                    for d in range(dim):
                        new_centroids[ki][d] /= counts[ki]
                else:
                    new_centroids[ki] = centroids[ki][:]
            centroids = new_centroids

        # Compute inertia
        inertia = 0.0
        for i, vec in enumerate(vectors):
            inertia += self._euclidean_distance(vec, centroids[labels[i]]) ** 2

        return {
            'labels': labels,
            'centroids': centroids,
            'inertia': inertia,
            'iterations': iterations,
        }

    # ------------------------------------------------------------------
    # DBSCAN
    # ------------------------------------------------------------------

    @api.model
    def _dbscan(self, vectors, epsilon, min_samples):
        """Density-based spatial clustering (DBSCAN).

        Returns:
            dict with keys: labels, n_clusters, n_noise
        """
        n = len(vectors)
        labels = [-1] * n  # -1 means noise/unvisited
        visited = [False] * n
        cluster_id = -1

        # Pre-compute neighbour lists for efficiency
        def region_query(idx):
            neighbours = []
            for j in range(n):
                if self._euclidean_distance(vectors[idx], vectors[j]) <= epsilon:
                    neighbours.append(j)
            return neighbours

        for i in range(n):
            if visited[i]:
                continue
            visited[i] = True
            neighbours = region_query(i)
            if len(neighbours) < min_samples:
                # Mark as noise (label stays -1)
                continue

            cluster_id += 1
            labels[i] = cluster_id

            # Expand cluster
            seed_set = list(neighbours)
            j = 0
            while j < len(seed_set):
                q = seed_set[j]
                if not visited[q]:
                    visited[q] = True
                    q_neighbours = region_query(q)
                    if len(q_neighbours) >= min_samples:
                        seed_set.extend(q_neighbours)
                if labels[q] == -1:
                    labels[q] = cluster_id
                j += 1

        n_noise = labels.count(-1)
        n_clusters = cluster_id + 1
        return {
            'labels': labels,
            'n_clusters': n_clusters,
            'n_noise': n_noise,
        }

    # ------------------------------------------------------------------
    # Hierarchical (Agglomerative)
    # ------------------------------------------------------------------

    @api.model
    def _hierarchical(self, vectors, n_clusters, linkage):
        """Agglomerative hierarchical clustering.

        Returns:
            dict with keys: labels, merge_history
        """
        n = len(vectors)
        if n_clusters <= 0:
            n_clusters = 1
        if n_clusters > n:
            n_clusters = n

        # Each point starts as its own cluster
        clusters = {i: [i] for i in range(n)}
        merge_history = []

        # Pre-compute pairwise distance matrix (upper triangle)
        dist_matrix = {}
        for i in range(n):
            for j in range(i + 1, n):
                dist_matrix[(i, j)] = self._euclidean_distance(vectors[i], vectors[j])

        next_id = n

        while len(clusters) > n_clusters:
            # Find the pair of clusters with minimum distance
            best_dist = float('inf')
            best_pair = None
            cluster_ids = sorted(clusters.keys())

            for ci_idx in range(len(cluster_ids)):
                for cj_idx in range(ci_idx + 1, len(cluster_ids)):
                    ci = cluster_ids[ci_idx]
                    cj = cluster_ids[cj_idx]
                    d = self._cluster_distance(
                        clusters[ci], clusters[cj], vectors, linkage,
                    )
                    if d < best_dist:
                        best_dist = d
                        best_pair = (ci, cj)

            if best_pair is None:
                break

            ci, cj = best_pair
            # Merge
            merged = clusters[ci] + clusters[cj]
            merge_history.append({
                'merged': [ci, cj],
                'distance': best_dist,
                'new_id': next_id,
            })
            del clusters[ci]
            del clusters[cj]
            clusters[next_id] = merged
            next_id += 1

        # Assign labels
        labels = [0] * n
        for label_idx, (_, members) in enumerate(sorted(clusters.items())):
            for member in members:
                labels[member] = label_idx

        return {
            'labels': labels,
            'merge_history': merge_history,
        }

    @api.model
    def _cluster_distance(self, cluster_a, cluster_b, vectors, linkage):
        """Compute distance between two clusters based on linkage method."""
        distances = []
        for i in cluster_a:
            for j in cluster_b:
                distances.append(self._euclidean_distance(vectors[i], vectors[j]))
        if not distances:
            return float('inf')
        if linkage == 'single':
            return min(distances)
        elif linkage == 'complete':
            return max(distances)
        else:  # average
            return sum(distances) / len(distances)

    # ------------------------------------------------------------------
    # Silhouette Score
    # ------------------------------------------------------------------

    @api.model
    def _silhouette_score(self, vectors, labels):
        """Compute mean silhouette coefficient.

        For each point, silhouette = (b - a) / max(a, b)
        where a = mean intra-cluster distance, b = mean nearest-cluster distance.
        """
        n = len(vectors)
        unique_labels = list(set(labels) - {-1})
        if len(unique_labels) < 2:
            return 0.0

        # Group indices by cluster
        cluster_indices = {}
        for i, label in enumerate(labels):
            if label == -1:
                continue
            cluster_indices.setdefault(label, []).append(i)

        silhouettes = []
        for i in range(n):
            if labels[i] == -1:
                continue
            my_cluster = labels[i]
            my_members = cluster_indices.get(my_cluster, [])

            # a(i) = mean distance to same cluster
            if len(my_members) <= 1:
                a_i = 0.0
            else:
                a_i = sum(
                    self._euclidean_distance(vectors[i], vectors[j])
                    for j in my_members if j != i
                ) / (len(my_members) - 1)

            # b(i) = min mean distance to any other cluster
            b_i = float('inf')
            for other_label in unique_labels:
                if other_label == my_cluster:
                    continue
                other_members = cluster_indices.get(other_label, [])
                if not other_members:
                    continue
                mean_dist = sum(
                    self._euclidean_distance(vectors[i], vectors[j])
                    for j in other_members
                ) / len(other_members)
                if mean_dist < b_i:
                    b_i = mean_dist

            if b_i == float('inf'):
                silhouettes.append(0.0)
            else:
                denom = max(a_i, b_i)
                silhouettes.append((b_i - a_i) / denom if denom > 0 else 0.0)

        return sum(silhouettes) / len(silhouettes) if silhouettes else 0.0

    # ------------------------------------------------------------------
    # Store Results
    # ------------------------------------------------------------------

    @api.model
    def _store_results(self, config, element_ids, labels, algo_result, duration):
        """Create SetDB structures (elements, edges, hierarchy, sigma-algebra)
        and return a setdb.clustering.result record.
        """
        Element = self.env['setdb.element']
        Edge = self.env['setdb.edge']
        Hierarchy = self.env['setdb.hierarchy']
        SigmaAlgebra = self.env['setdb.sigma_algebra']
        Result = self.env['setdb.clustering.result']

        timestamp = fields.Datetime.now()
        result_name = "%s [%s]" % (config.name, timestamp)

        # Group elements by cluster label
        cluster_map = {}  # label -> list of element_ids
        for idx, label in enumerate(labels):
            cluster_map.setdefault(label, []).append(element_ids[idx])

        # 1. Create root set element
        root_element = Element.create({
            'name': "%s Clusters" % config.name,
            'element_type': 'set',
            'metadata_json': json.dumps({
                'clustering_config': config.name,
                'algorithm': config.algorithm,
                'computed_at': str(timestamp),
            }),
        })

        # 2. Create cluster set elements + edges
        cluster_elements = []
        cluster_sizes = {}
        centroids = algo_result.get('centroids', [])
        sorted_labels = sorted(cluster_map.keys())

        for label in sorted_labels:
            member_ids = cluster_map[label]
            if label == -1:
                cluster_name = "Noise"
            else:
                cluster_name = "Cluster %d" % label

            meta = {'cluster_label': label, 'size': len(member_ids)}
            if centroids and label >= 0 and label < len(centroids):
                meta['centroid'] = centroids[label]

            cluster_elem = Element.create({
                'name': cluster_name,
                'element_type': 'set',
                'metadata_json': json.dumps(meta),
            })
            cluster_elements.append((label, cluster_elem, member_ids))
            cluster_sizes[cluster_name] = len(member_ids)

        # 3. Create edges: root -> clusters
        edge_vals = []
        for ordinal, (label, cluster_elem, _member_ids) in enumerate(cluster_elements):
            edge_vals.append({
                'parent_id': root_element.id,
                'child_id': cluster_elem.id,
                'ordinal': ordinal,
            })

        # 3b. Create edges: clusters -> primitives
        for label, cluster_elem, member_ids in cluster_elements:
            for ord_idx, eid in enumerate(member_ids):
                edge_vals.append({
                    'parent_id': cluster_elem.id,
                    'child_id': eid,
                    'ordinal': ord_idx,
                })

        Edge.create(edge_vals)

        # 4. Create hierarchy
        hierarchy = Hierarchy.create({
            'name': result_name,
            'description': "Clustering result for '%s' using %s" % (
                config.name, config.algorithm,
            ),
            'root_id': root_element.id,
            'hierarchy_type': 'tree',
        })

        # 5. Create sigma-algebra with enforce_partition
        member_set_ids = [ce.id for (_, ce, _) in cluster_elements]
        sigma = SigmaAlgebra.create({
            'name': "SA: %s" % result_name,
            'omega_id': root_element.id,
            'enforce_partition': True,
            'validate_on_modify': False,
            'member_ids': [fields.Command.set(member_set_ids)],
        })

        # Compute stats
        unique_real = set(labels) - {-1}
        n_clusters = len(unique_real)
        n_noise = labels.count(-1)
        n_elements = len(element_ids)

        diagnostics = {
            'algorithm': config.algorithm,
            'iterations': algo_result.get('iterations', 0),
            'n_clusters': n_clusters,
            'n_elements': n_elements,
            'n_noise': n_noise,
        }
        if 'merge_history' in algo_result:
            diagnostics['merge_history_length'] = len(algo_result['merge_history'])

        result = Result.create({
            'config_id': config.id,
            'name': result_name,
            'root_element_id': root_element.id,
            'hierarchy_id': hierarchy.id,
            'sigma_algebra_id': sigma.id,
            'n_clusters': n_clusters,
            'n_elements': n_elements,
            'n_noise': n_noise,
            'silhouette_score': algo_result.get('silhouette_score', 0.0),
            'inertia': algo_result.get('inertia', 0.0),
            'centroids_json': json.dumps(algo_result.get('centroids', [])),
            'cluster_sizes_json': json.dumps(cluster_sizes),
            'diagnostics_json': json.dumps(diagnostics),
            'computed_at': timestamp,
            'duration_seconds': duration,
        })

        return result
