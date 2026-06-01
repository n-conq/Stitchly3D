import json
import logging
import os
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger(__name__)

try:
    import jsonschema
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False

_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema-cutting-pattern.json')


def _load_schema() -> Optional[Dict]:
    try:
        with open(_SCHEMA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def migrate_v1_to_v2(data: Dict) -> Dict:
    """Convert a v1.0 file (inline vertex coords per edge) to v2.0 (global vertex/edge tables)."""
    vertex_index: Dict[Tuple, str] = {}
    vertices: List[Dict] = []
    edges: List[Dict] = []

    def find_or_create(x: float, y: float) -> str:
        key = (round(x, 5), round(y, 5))
        if key in vertex_index:
            return vertex_index[key]
        vid = f"v_{len(vertices) + 1}"
        vertices.append({"id": vid, "x": key[0], "y": key[1]})
        vertex_index[key] = vid
        return vid

    new_parts = []
    for part in data.get('parts', []):
        edge_ids = []
        for edge in part.get('edges', []):
            v1id = find_or_create(edge['vertex1']['x'], edge['vertex1']['y'])
            v2id = find_or_create(edge['vertex2']['x'], edge['vertex2']['y'])
            new_edge: Dict[str, Any] = {"id": edge['id'], "v1": v1id, "v2": v2id}
            if edge.get('standalone'):
                new_edge['type'] = 'construction'
            elif edge.get('type'):
                new_edge['type'] = edge['type']
            else:
                new_edge['type'] = 'outline'
            edges.append(new_edge)
            edge_ids.append(edge['id'])
        new_part: Dict[str, Any] = {"id": part['id'], "edgeIds": edge_ids}
        for key in ('onFold', 'grainlineRotation'):
            if key in part:
                new_part[key] = part[key]
        new_parts.append(new_part)

    return {
        "version": "2.0",
        "units": "cm",
        "vertices": vertices,
        "edges": edges,
        "parts": new_parts,
        "stitches": data.get('stitches', []),
        "seams": data.get('seams', []),
    }


class JsonPieceManager:
    """Manages pattern piece data stored in JSON v2.0 format."""

    def __init__(self, json_file: str):
        self.json_file = json_file
        self.selected_part_id: Optional[str] = None

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('version', '1.0') != '2.0':
                data = migrate_v1_to_v2(data)
                logger.info("Migrated '%s' from v1.0 to v2.0 — saving migrated file.", json_file)
            self.json_data = data
        except FileNotFoundError:
            self.json_data = {
                "version": "2.0",
                "units": "cm",
                "vertices": [], "edges": [], "parts": [],
                "stitches": [], "seams": [],
            }

        for key in ('vertices', 'edges', 'stitches', 'seams'):
            if key not in self.json_data:
                self.json_data[key] = []

        self._validate(self.json_data, json_file)

    @staticmethod
    def _validate(data: Dict, source: str) -> None:
        if _JSONSCHEMA_AVAILABLE:
            schema = _load_schema()
            if schema is not None:
                try:
                    jsonschema.validate(instance=data, schema=schema)
                except jsonschema.ValidationError as exc:
                    logger.warning("'%s' failed schema validation: %s", source, exc.message)
            else:
                logger.warning("schema-cutting-pattern.json not found — skipping schema validation")
        else:
            logger.warning("jsonschema not installed — skipping schema validation")

        # Referential integrity — not expressible in JSON Schema 2020-12
        vertex_ids = {v['id'] for v in data.get('vertices', [])}
        edge_ids   = {e['id'] for e in data.get('edges', [])}

        for edge in data.get('edges', []):
            for key in ('v1', 'v2'):
                if edge.get(key) not in vertex_ids:
                    logger.warning("edge '%s' %s='%s' not found in vertices",
                                   edge['id'], key, edge.get(key))

        for part in data.get('parts', []):
            for eid in part.get('edgeIds', []):
                if eid not in edge_ids:
                    logger.warning("part '%s' edgeId '%s' not found in edges",
                                   part['id'], eid)

        for seam in data.get('seams', []):
            for entry in seam.get('sewnEdges', []):
                if entry['id'] not in edge_ids:
                    logger.warning("seam '%s' sewnEdge '%s' not found in edges",
                                   seam['id'], entry['id'])


    def _vertex_map(self) -> Dict[str, Dict]:
        return {v['id']: v for v in self.json_data['vertices']}

    def _edge_map(self) -> Dict[str, Dict]:
        return {e['id']: e for e in self.json_data['edges']}

    def _find_or_create_vertex(self, x: float, y: float) -> str:
        key = (round(x, 5), round(y, 5))
        for v in self.json_data['vertices']:
            if (round(v['x'], 5), round(v['y'], 5)) == key:
                return v['id']
        vid = f"v_{len(self.json_data['vertices']) + 1}"
        self.json_data['vertices'].append({"id": vid, "x": key[0], "y": key[1]})
        return vid

    def _next_edge_seq(self, part_id: str) -> int:
        prefix = f"edge_{part_id.replace('part_', '')}_"
        nums = []
        for e in self.json_data['edges']:
            if e['id'].startswith(prefix):
                tail = e['id'][len(prefix):]
                if tail.isdigit():
                    nums.append(int(tail))
        return max(nums, default=0) + 1

    def _resolve_edge(self, raw: Dict, vmap: Dict) -> Optional[Dict]:
        """Return a resolved edge dict with vertex1/vertex2 coords and IDs, or None on missing refs.

        The vertex sub-dicts carry the storage ID so geometry.py can use string
        identity instead of floating-point coordinate comparison.
        """
        v1 = vmap.get(raw['v1'])
        v2 = vmap.get(raw['v2'])
        if v1 is None or v2 is None:
            return None
        resolved: Dict[str, Any] = {
            'id':      raw['id'],
            'vertex1': {'id': raw['v1'], 'x': v1['x'], 'y': v1['y']},
            'vertex2': {'id': raw['v2'], 'x': v2['x'], 'y': v2['y']},
        }
        edge_type = raw.get('type', 'outline')
        if edge_type != 'outline':
            resolved['type'] = edge_type
        return resolved


    def get_all_parts(self) -> List[Dict[str, Any]]:
        return self.json_data.get('parts', [])

    def get_part_by_id(self, part_id: str) -> Optional[Dict[str, Any]]:
        for part in self.json_data['parts']:
            if part['id'] == part_id:
                return part
        return None

    def select_part(self, part_id: str) -> bool:
        if self.get_part_by_id(part_id):
            self.selected_part_id = part_id
            return True
        return False

    def get_selected_part(self) -> Optional[Dict[str, Any]]:
        if self.selected_part_id:
            return self.get_part_by_id(self.selected_part_id)
        return None

    def get_part_edges(self, part_id: str) -> List[Dict[str, Any]]:
        """Return resolved edge dicts (vertex1/vertex2 coords) for a part's edgeIds.

        The returned shape matches the old inline format so geometry.py and
        the UI layer work without modification.
        """
        part = self.get_part_by_id(part_id)
        if not part:
            return []
        vmap = self._vertex_map()
        emap = self._edge_map()
        result = []
        for eid in part.get('edgeIds', []):
            raw = emap.get(eid)
            if raw is None:
                continue
            resolved = self._resolve_edge(raw, vmap)
            if resolved is not None:
                result.append(resolved)
        return result

    def get_part_outline(self, part_id: str) -> Tuple[List[float], List[float]]:
        outline = [e for e in self.get_part_edges(part_id) if e.get('type', 'outline') == 'outline']
        return [e['vertex1']['x'] for e in outline], [e['vertex1']['y'] for e in outline]


    def get_edge_by_id(self, edge_id: str) -> Tuple[Optional[str], Optional[Dict]]:
        """Return (part_id, resolved_edge_dict) or (None, None)."""
        raw = self._edge_map().get(edge_id)
        if raw is None:
            return None, None
        resolved = self._resolve_edge(raw, self._vertex_map())
        if resolved is None:
            return None, None
        part_id = next(
            (p['id'] for p in self.json_data['parts'] if edge_id in p.get('edgeIds', [])),
            None
        )
        return part_id, resolved


    def delete_edge(self, part_id: str, edge_id: str) -> Tuple[bool, str]:
        part = self.get_part_by_id(part_id)
        if not part or edge_id not in part.get('edgeIds', []):
            return False, "Edge not found"
        part['edgeIds'] = [eid for eid in part['edgeIds'] if eid != edge_id]
        self.json_data['edges'] = [e for e in self.json_data['edges'] if e['id'] != edge_id]
        self.save_json()
        return True, f"✓ Deleted edge '{edge_id}'"

    def add_edge(self, part_id: str, vertex1: dict, vertex2: dict) -> Tuple[bool, str]:
        part = self.get_part_by_id(part_id)
        if not part:
            return False, "Part not found"
        v1id = self._find_or_create_vertex(vertex1['x'], vertex1['y'])
        v2id = self._find_or_create_vertex(vertex2['x'], vertex2['y'])
        seq = self._next_edge_seq(part_id)
        new_eid = f"edge_{part_id.replace('part_', '')}_{seq}"
        self.json_data['edges'].append({"id": new_eid, "v1": v1id, "v2": v2id, "type": "construction"})
        part.setdefault('edgeIds', []).append(new_eid)
        self.save_json()
        return True, f"✓ Added edge '{new_eid}'"

    def copy_selected_part(self) -> Tuple[bool, str]:
        if self.selected_part_id is None:
            return False, "No part selected"
        part = self.get_selected_part()
        if not part:
            return False, "Selected part not found"

        base_name = part['id'].replace('part_', '')
        copy_count = sum(1 for p in self.json_data['parts']
                         if p['id'].startswith(f"part_{base_name}_copy"))
        new_part_id = f"part_{base_name}_copy_{copy_count + 1}"

        emap = self._edge_map()
        new_edge_ids = []
        for i, eid in enumerate(part.get('edgeIds', [])):
            raw = emap.get(eid)
            if raw is None:
                continue
            new_eid = f"edge_{new_part_id.replace('part_', '')}_{i + 1}"
            new_edge: Dict[str, Any] = {"id": new_eid, "v1": raw['v1'], "v2": raw['v2'],
                                         "type": raw.get('type', 'outline')}
            self.json_data['edges'].append(new_edge)
            new_edge_ids.append(new_eid)

        new_part: Dict[str, Any] = {"id": new_part_id, "edgeIds": new_edge_ids}
        for key in ('onFold', 'grainlineRotation'):
            if key in part:
                new_part[key] = part[key]
        self.json_data['parts'].append(new_part)
        self.save_json()
        return True, f"✓ Copied part as '{new_part_id}'"

    def mirror_selected_part(self, axis: str = 'vertical') -> Tuple[bool, str]:
        if self.selected_part_id is None:
            return False, "No part selected"
        part = self.get_selected_part()
        if not part:
            return False, "Selected part not found"
        if axis not in ('vertical', 'horizontal'):
            return False, f"Invalid axis '{axis}'. Use 'vertical' or 'horizontal'"

        resolved = self.get_part_edges(self.selected_part_id)
        all_x = [e['vertex1']['x'] for e in resolved]
        all_y = [e['vertex1']['y'] for e in resolved]
        center_x = (max(all_x) + min(all_x)) / 2
        center_y = (max(all_y) + min(all_y)) / 2

        base_name = part['id'].replace('part_', '')
        mirror_count = sum(1 for p in self.json_data['parts']
                           if p['id'].startswith(f"part_{base_name}_mirror"))
        new_part_id = f"part_{base_name}_mirror_{axis}_{mirror_count + 1}"

        def reflect(x: float, y: float) -> Tuple[float, float]:
            if axis == 'vertical':
                return round(2 * center_x - x, 5), y
            return x, round(2 * center_y - y, 5)

        resolved_map = {e['id']: e for e in resolved}
        emap = self._edge_map()
        new_edge_ids = []
        # Reverse + swap v1/v2 + reflect to maintain correct winding
        for i, eid in enumerate(reversed(part.get('edgeIds', []))):
            raw = emap.get(eid)
            res = resolved_map.get(eid)
            if raw is None or res is None:
                continue
            rx1, ry1 = reflect(res['vertex2']['x'], res['vertex2']['y'])
            rx2, ry2 = reflect(res['vertex1']['x'], res['vertex1']['y'])
            v1id = self._find_or_create_vertex(rx1, ry1)
            v2id = self._find_or_create_vertex(rx2, ry2)
            new_eid = f"edge_{new_part_id.replace('part_', '')}_{i + 1}"
            new_edge: Dict[str, Any] = {"id": new_eid, "v1": v1id, "v2": v2id,
                                         "type": raw.get('type', 'outline')}
            self.json_data['edges'].append(new_edge)
            new_edge_ids.append(new_eid)

        new_part: Dict[str, Any] = {"id": new_part_id, "edgeIds": new_edge_ids}
        for key in ('onFold', 'grainlineRotation'):
            if key in part:
                new_part[key] = part[key]
        self.json_data['parts'].append(new_part)
        self.save_json()
        return True, f"✓ Created mirrored part '{new_part_id}' ({axis})"

    def mirror_edge(self, edge_id: str, axis: str, axis_value: float) -> Tuple[bool, str]:
        part_id, resolved = self.get_edge_by_id(edge_id)
        if part_id is None:
            return False, "Edge not found"
        part = self.get_part_by_id(part_id)

        if axis == 'vertical':
            rx1 = round(2 * axis_value - resolved['vertex1']['x'], 5)
            ry1 = resolved['vertex1']['y']
            rx2 = round(2 * axis_value - resolved['vertex2']['x'], 5)
            ry2 = resolved['vertex2']['y']
        elif axis == 'horizontal':
            rx1 = resolved['vertex1']['x']
            ry1 = round(2 * axis_value - resolved['vertex1']['y'], 5)
            rx2 = resolved['vertex2']['x']
            ry2 = round(2 * axis_value - resolved['vertex2']['y'], 5)
        else:
            return False, f"Invalid axis '{axis}'"

        v1id = self._find_or_create_vertex(rx1, ry1)
        v2id = self._find_or_create_vertex(rx2, ry2)
        seq = self._next_edge_seq(part_id)
        new_eid = f"edge_{part_id.replace('part_', '')}_{seq}"
        self.json_data['edges'].append({"id": new_eid, "v1": v1id, "v2": v2id, "type": "mirror"})
        part.setdefault('edgeIds', []).append(new_eid)
        self.save_json()
        return True, f"✓ Mirrored edge as '{new_eid}' ({axis} at {axis_value})"

    def delete_selected_part(self) -> Tuple[bool, str]:
        if self.selected_part_id is None:
            return False, "No part selected"
        part = self.get_part_by_id(self.selected_part_id)
        if not part:
            return False, "Part not found"

        # Only remove edges not referenced by any other part
        other_edge_ids: set = set()
        for p in self.json_data['parts']:
            if p['id'] != self.selected_part_id:
                other_edge_ids.update(p.get('edgeIds', []))
        to_delete = set(part.get('edgeIds', [])) - other_edge_ids
        self.json_data['edges'] = [e for e in self.json_data['edges']
                                   if e['id'] not in to_delete]
        self.json_data['parts'] = [p for p in self.json_data['parts']
                                   if p['id'] != self.selected_part_id]
        self.selected_part_id = None
        self.save_json()
        return True, "✓ Part deleted"


    def add_stitch(self, stitch_id: str, stitch_type: str) -> Tuple[bool, str]:
        self.json_data['stitches'].append({"id": stitch_id, "stitchType": stitch_type})
        self.save_json()
        return True, f"✓ Added stitch '{stitch_id}'"

    def get_all_stitches(self) -> List[Dict[str, Any]]:
        return self.json_data.get('stitches', [])

    def stitch_exists(self, stitch_id: str) -> bool:
        return any(s['id'] == stitch_id for s in self.get_all_stitches())


    def add_seam(self, seam_data: Dict[str, Any]) -> Tuple[bool, str]:
        self.json_data['seams'].append(seam_data)
        self.save_json()
        return True, f"✓ Added seam '{seam_data['id']}'"

    def get_all_seams(self) -> List[Dict[str, Any]]:
        return self.json_data.get('seams', [])


    def save_json(self):
        with open(self.json_file, 'w', encoding='utf-8') as f:
            json.dump(self.json_data, f, indent=4, ensure_ascii=False)
