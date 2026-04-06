import json
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)


class SetDBBridgeEngine(models.AbstractModel):
    _name = 'setdb.bridge.engine'
    _description = 'SetDB Bridge Sync Engine'

    @api.model
    def sync_bridge(self, bridge):
        """Main sync method: read source records and create/update SetDB elements.

        Returns a dict with sync stats: {created: N, updated: N, skipped: N}.
        """
        stats = {'created': 0, 'updated': 0, 'skipped': 0}

        source_model = self.env[bridge.source_model_id.model]
        domain = safe_eval(bridge.domain_filter or '[]')
        source_records = source_model.search(domain)

        if not source_records:
            return stats

        Element = self.env['setdb.element']
        Edge = self.env['setdb.edge']

        # Preload mapping configuration
        name_mapping = bridge.mapping_ids.filtered(lambda m: m.mapping_type == 'name')
        metadata_mappings = bridge.mapping_ids.filtered(lambda m: m.mapping_type == 'metadata')
        parent_mapping = bridge.mapping_ids.filtered(lambda m: m.mapping_type == 'parent')
        type_mapping = bridge.mapping_ids.filtered(lambda m: m.mapping_type == 'element_type')

        # Build target container (hierarchy root or auto-created set)
        target_set = None
        if bridge.target_hierarchy_id:
            target_set = bridge.target_hierarchy_id.root_id

        for record in source_records:
            try:
                element_vals = self._build_element_vals(
                    record, name_mapping, metadata_mappings, type_mapping,
                )
                if not element_vals.get('name'):
                    stats['skipped'] += 1
                    continue

                # Check for existing element by metadata source reference
                metadata = json.loads(element_vals.get('metadata_json', '{}') or '{}')
                existing = Element.search([
                    ('name', '=', element_vals['name']),
                    ('element_type', '=', element_vals.get('element_type', 'primitive')),
                ], limit=1)

                if existing:
                    existing.write(element_vals)
                    element = existing
                    stats['updated'] += 1
                else:
                    element = Element.create(element_vals)
                    stats['created'] += 1

                # Create edge to target hierarchy if specified
                if target_set and not Edge.search([
                    ('parent_id', '=', target_set.id),
                    ('child_id', '=', element.id),
                ], limit=1):
                    Edge.create({
                        'parent_id': target_set.id,
                        'child_id': element.id,
                    })

                # Handle parent mapping
                if parent_mapping:
                    self._handle_parent_mapping(record, element, parent_mapping, Edge)

                # Handle dimension mappings
                for dim in bridge.dimension_ids:
                    self._handle_dimension(record, element, dim, Edge)

            except Exception:
                _logger.exception(
                    'Bridge sync error for record %s (id=%d)',
                    record.display_name, record.id,
                )
                stats['skipped'] += 1

        return stats

    @api.model
    def preview_bridge(self, bridge):
        """Same analysis as sync but read-only -- returns preview stats without writing."""
        stats = {'created': 0, 'updated': 0, 'skipped': 0}

        source_model = self.env[bridge.source_model_id.model]
        domain = safe_eval(bridge.domain_filter or '[]')
        source_records = source_model.search(domain)

        if not source_records:
            return stats

        Element = self.env['setdb.element']
        name_mapping = bridge.mapping_ids.filtered(lambda m: m.mapping_type == 'name')
        metadata_mappings = bridge.mapping_ids.filtered(lambda m: m.mapping_type == 'metadata')
        type_mapping = bridge.mapping_ids.filtered(lambda m: m.mapping_type == 'element_type')

        for record in source_records:
            try:
                element_vals = self._build_element_vals(
                    record, name_mapping, metadata_mappings, type_mapping,
                )
                if not element_vals.get('name'):
                    stats['skipped'] += 1
                    continue

                existing = Element.search([
                    ('name', '=', element_vals['name']),
                    ('element_type', '=', element_vals.get('element_type', 'primitive')),
                ], limit=1)

                if existing:
                    stats['updated'] += 1
                else:
                    stats['created'] += 1
            except Exception:
                stats['skipped'] += 1

        return stats

    def _build_element_vals(self, record, name_mapping, metadata_mappings, type_mapping):
        """Build element values dict from a source record and mappings."""
        vals = {'element_type': 'primitive'}

        # Name mapping
        if name_mapping:
            field_name = name_mapping[0].source_field_id.name
            vals['name'] = str(getattr(record, field_name, '') or '')
        else:
            vals['name'] = record.display_name or ''

        # Element type mapping
        if type_mapping:
            field_name = type_mapping[0].source_field_id.name
            raw = getattr(record, field_name, 'primitive')
            if raw in ('primitive', 'set', 'sequence'):
                vals['element_type'] = raw

        # Metadata mappings
        metadata = {
            '_source_model': record._name,
            '_source_id': record.id,
        }
        for mapping in metadata_mappings:
            field_name = mapping.source_field_id.name
            key = mapping.metadata_key or field_name
            value = getattr(record, field_name, None)
            if hasattr(value, 'id'):
                # Many2one: store id and display name
                metadata[key] = {'id': value.id, 'name': value.display_name} if value else None
            elif hasattr(value, 'ids'):
                # Many2many/One2many: store ids
                metadata[key] = value.ids if value else []
            else:
                metadata[key] = str(value) if value is not None else None

        vals['metadata_json'] = json.dumps(metadata, default=str)
        return vals

    def _handle_parent_mapping(self, record, element, parent_mapping, Edge):
        """Create edge from parent element to the current element."""
        field_name = parent_mapping[0].source_field_id.name
        parent_ref = getattr(record, field_name, None)
        if not parent_ref:
            return

        Element = self.env['setdb.element']
        parent_name = parent_ref.display_name if hasattr(parent_ref, 'display_name') else str(parent_ref)

        parent_element = Element.search([('name', '=', parent_name)], limit=1)
        if parent_element and parent_element.element_type != 'primitive':
            if not Edge.search([
                ('parent_id', '=', parent_element.id),
                ('child_id', '=', element.id),
            ], limit=1):
                Edge.create({
                    'parent_id': parent_element.id,
                    'child_id': element.id,
                })

    def _handle_dimension(self, record, element, dim, Edge):
        """Handle a dimension mapping: link element to dimension hierarchy member."""
        field_name = dim.odoo_field_id.name
        value = getattr(record, field_name, None)

        if not value:
            return

        Element = self.env['setdb.element']

        # Period dimension: match date to period hierarchy
        if dim.period_config_id and hasattr(value, 'strftime'):
            self._handle_period_dimension(element, value, dim, Edge)
            return

        # Many2one dimension: find or create hierarchy member
        if hasattr(value, 'display_name'):
            member_name = value.display_name
            target_hierarchy = dim.target_hierarchy_id

            member = Element.search([('name', '=', member_name)], limit=1)

            if not member and dim.auto_create_hierarchy:
                member = Element.create({
                    'name': member_name,
                    'element_type': 'primitive',
                    'metadata_json': json.dumps({
                        '_source_model': value._name,
                        '_source_id': value.id,
                    }),
                })
                # Add to hierarchy if configured
                if target_hierarchy:
                    Edge.create({
                        'parent_id': target_hierarchy.root_id.id,
                        'child_id': member.id,
                    })

            if member:
                if not Edge.search([
                    ('parent_id', '=', member.id),
                    ('child_id', '=', element.id),
                ], limit=1) and member.element_type != 'primitive':
                    Edge.create({
                        'parent_id': member.id,
                        'child_id': element.id,
                    })
                elif not Edge.search([
                    ('parent_id', '=', element.id),
                    ('child_id', '=', member.id),
                ], limit=1):
                    # Store as metadata edge link
                    metadata = json.loads(element.metadata_json or '{}')
                    metadata['_dim_%s' % field_name] = member.id
                    element.write({'metadata_json': json.dumps(metadata, default=str)})

    def _handle_period_dimension(self, element, date_value, dim, Edge):
        """Match a date value to a period hierarchy member via date_from/date_to metadata."""
        Element = self.env['setdb.element']
        target_hierarchy = dim.target_hierarchy_id
        if not target_hierarchy:
            return

        date_str = date_value.strftime('%Y-%m-%d') if hasattr(date_value, 'strftime') else str(date_value)

        # Search for period elements within the hierarchy that contain this date
        root = target_hierarchy.root_id
        period_members = root.members() if root else Element.browse()

        for period in period_members:
            if not period.metadata_json:
                continue
            try:
                meta = json.loads(period.metadata_json)
            except (json.JSONDecodeError, TypeError):
                continue

            date_from = meta.get('date_from', '')
            date_to = meta.get('date_to', '')
            if date_from and date_to and date_from <= date_str <= date_to:
                if not Edge.search([
                    ('parent_id', '=', period.id),
                    ('child_id', '=', element.id),
                ], limit=1):
                    Edge.create({
                        'parent_id': period.id,
                        'child_id': element.id,
                    })
                return
