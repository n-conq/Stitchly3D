"""
Pure geometric functions for edge/vertex topology on pattern pieces.

All functions are stateless — they take plain edge/vertex dicts and return
results without touching any plotter, manager, or matplotlib state.
This makes them independently unit-testable.

Edge dict shape:  {'id': str,
                   'vertex1': {'id': str, 'x': float, 'y': float},
                   'vertex2': {'id': str, 'x': float, 'y': float},
                   'type': 'outline' | 'mirror' | 'construction'  (optional, defaults to 'outline')}

Vertex identity is established by the string 'id' field, not by coordinate
comparison. The model layer guarantees that coordinates stored in the vertex
table are already canonicalised (rounded to 5 decimal places at creation time),
so there is no need for floating-point comparison here.
"""
import math
from typing import Dict, List, Tuple, Optional


def rotate_edges_for_display(edges: List[Dict], angle_deg: float) -> List[Dict]:
    """Return a copy of *edges* with all vertex x/y rotated *angle_deg* degrees
    counter-clockwise around the centroid of all vertex positions.

    Intended for display-only grain-line alignment.  Vertex 'id' fields are
    preserved unchanged so ID-based topology helpers still work on the result.
    Callers must NOT write the rotated coordinates back to the model.
    """
    if not edges or angle_deg == 0.0:
        return edges

    all_x = [e['vertex1']['x'] for e in edges] + [e['vertex2']['x'] for e in edges]
    all_y = [e['vertex1']['y'] for e in edges] + [e['vertex2']['y'] for e in edges]
    cx = sum(all_x) / len(all_x)
    cy = sum(all_y) / len(all_y)

    rad = math.radians(angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    def _rot(x: float, y: float) -> Tuple[float, float]:
        dx, dy = x - cx, y - cy
        return cx + cos_a * dx - sin_a * dy, cy + sin_a * dx + cos_a * dy

    result = []
    for e in edges:
        v1, v2 = e['vertex1'], e['vertex2']
        rx1, ry1 = _rot(v1['x'], v1['y'])
        rx2, ry2 = _rot(v2['x'], v2['y'])
        new_e = dict(e)
        new_e['vertex1'] = {**v1, 'x': rx1, 'y': ry1}
        new_e['vertex2'] = {**v2, 'x': rx2, 'y': ry2}
        result.append(new_e)
    return result


def outline_edges(edges: List[Dict]) -> List[Dict]:
    """Return only edges that form the part outline (type='outline' or absent)."""
    return [e for e in edges if e.get('type', 'outline') == 'outline']


def vertex_path(all_edges: List[Dict]) -> List[str]:
    """Return ordered vertex IDs around the closed outline.

    Position i corresponds to outline edge i: edge[i] runs from
    path[i] to path[(i+1) % n].  Standalone edges are excluded.
    """
    return [e['vertex1']['id'] for e in outline_edges(all_edges)]


def find_vertex_index(path: List[str], vtx: Dict) -> Optional[int]:
    """Return the index in *path* whose vertex ID matches *vtx*, or None."""
    vid = vtx['id']
    for i, v in enumerate(path):
        if v == vid:
            return i
    return None


def find_edge_between(edges: List[Dict], v1: Dict, v2: Dict) -> Optional[str]:
    """Return the edge id of an edge directly connecting v1 and v2 (either
    direction), or None if no such edge exists."""
    id1, id2 = v1['id'], v2['id']
    for e in edges:
        e1, e2 = e['vertex1']['id'], e['vertex2']['id']
        if (e1 == id1 and e2 == id2) or (e1 == id2 and e2 == id1):
            return e['id']
    return None


def walk_to_vertex(
    all_edges: List[Dict],
    start_vtx: Dict,
    dir_vtx: Dict,
    end_vtx: Dict,
) -> Tuple[Optional[List[str]], str]:
    """Walk from start_vtx toward dir_vtx through any edge until end_vtx is
    reached.  Traverses all edges including standalone ones.  Used when
    end_vtx is not on the outline (e.g. a mirrored edge endpoint).
    """
    adj: Dict[str, List[Tuple[str, str]]] = {}
    for e in all_edges:
        c1, c2 = e['vertex1']['id'], e['vertex2']['id']
        if c1 != c2:
            adj.setdefault(c1, []).append((c2, e['id']))
            adj.setdefault(c2, []).append((c1, e['id']))

    end_id   = end_vtx['id']
    start_id = start_vtx['id']
    dir_id   = dir_vtx['id']

    collected: List[str] = []
    visited = {start_id}

    for nb, eid in adj.get(start_id, []):
        if nb == dir_id:
            collected.append(eid)
            break
    else:
        return None, "Direction vertex not adjacent to start."

    visited.add(dir_id)
    current = dir_id

    for _ in range(len(all_edges)):
        if current == end_id:
            return collected, f"{len(collected)} edge(s) selected."
        unvisited = [(nb, eid) for nb, eid in adj.get(current, []) if nb not in visited]
        if not unvisited:
            break
        next_id, eid = unvisited[0]
        collected.append(eid)
        visited.add(next_id)
        current = next_id

    if current == end_id:
        return collected, f"{len(collected)} edge(s) selected."
    return None, "Cannot reach end vertex from here."


def edges_on_path(
    all_edges: List[Dict],
    start_vtx: Dict,
    dir_vtx: Dict,
    end_vtx: Dict,
) -> Tuple[Optional[List[str]], str]:
    """Return edge IDs from start_vtx to end_vtx, traversing in the direction
    of dir_vtx.

    dir_vtx must be adjacent to start_vtx on the outline.  If either
    start_vtx or dir_vtx is not on the outline (e.g. a standalone/mirrored
    vertex), or if end_vtx is off the outline, falls back to walk_to_vertex
    which traverses all edges including standalone ones.

    Returns (edge_id_list, message).  On failure, edge_id_list is None.
    """
    oe   = outline_edges(all_edges)
    path = [e['vertex1']['id'] for e in oe]
    n    = len(path)

    start_i = find_vertex_index(path, start_vtx)
    dir_i   = find_vertex_index(path, dir_vtx)
    end_i   = find_vertex_index(path, end_vtx)

    if start_i is None or dir_i is None:
        # One or both vertices are off the outline (standalone/mirrored).
        return walk_to_vertex(all_edges, start_vtx, dir_vtx, end_vtx)

    forward  = (dir_i == (start_i + 1) % n)
    backward = (dir_i == (start_i - 1) % n)
    if not forward and not backward:
        return None, "Direction vertex must be adjacent to the start vertex."

    if end_i is None:
        # End vertex is off the outline (e.g. a mirrored standalone vertex).
        return walk_to_vertex(all_edges, start_vtx, dir_vtx, end_vtx)

    selected: List[str] = []
    i = start_i
    while i != end_i:
        if forward:
            selected.append(oe[i]['id'])
            i = (i + 1) % n
        else:
            i = (i - 1) % n
            selected.append(oe[i]['id'])
        if len(selected) > n:
            return None, "Could not reach end vertex — path wraps more than once."

    if not selected:
        return None, "Start and end vertex are the same."
    return selected, f"{len(selected)} edge(s) selected."
