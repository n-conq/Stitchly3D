import json
from typing import Dict, Any, Callable, List, Optional, Tuple

from seamly_parser import get_piece_outline_coords


def _build_vertex_registry() -> Tuple[List[Dict], Callable]:
    """Return (vertices list, find_or_create callable) sharing the same backing store."""
    vertices: List[Dict] = []
    index: Dict[Tuple[float, float], str] = {}

    def find_or_create(x: float, y: float) -> str:
        key = (round(x, 5), round(y, 5))
        if key in index:
            return index[key]
        vid = f"v_{len(vertices) + 1}"
        vertices.append({"id": vid, "x": key[0], "y": key[1]})
        index[key] = vid
        return vid

    return vertices, find_or_create


def convert_piece_to_part(piece, find_or_create: Callable,
                          edges_out: List[Dict]) -> Optional[Dict[str, Any]]:
    """Convert a parsed Seamly2D piece into a v2.0 part dict.

    Vertices are deduplicated via find_or_create; new edge dicts are appended
    to edges_out. Returns the part dict (with edgeIds), or None if the piece
    has fewer than 2 outline points.
    """
    outline_x, outline_y = get_piece_outline_coords(piece)

    if len(outline_x) < 2:
        return None

    # Drop closing duplicate vertex produced by some parsers (first == last point).
    if (round(outline_x[-1], 5) == round(outline_x[0], 5)
            and round(outline_y[-1], 5) == round(outline_y[0], 5)):
        outline_x = outline_x[:-1]
        outline_y = outline_y[:-1]

    if len(outline_x) < 2:
        return None

    edge_ids = []
    for i in range(len(outline_x)):
        next_i = (i + 1) % len(outline_x)
        v1id = find_or_create(outline_x[i],      outline_y[i])
        v2id = find_or_create(outline_x[next_i], outline_y[next_i])
        eid  = f"edge_{piece.id}_{i + 1}"
        edges_out.append({"id": eid, "v1": v1id, "v2": v2id, "type": "outline"})
        edge_ids.append(eid)

    part: Dict[str, Any] = {
        "id":      f"part_{piece.name}" if hasattr(piece, 'name') else f"part_{piece.id}",
        "edgeIds": edge_ids,
    }
    if hasattr(piece, 'onFold'):
        part["onFold"] = piece.onFold
    if hasattr(piece, 'grainlineRotation'):
        part["grainlineRotation"] = piece.grainlineRotation

    return part


def pieces_to_json(pieces_dict: Dict[str, Any], output_file: str = None) -> Dict[str, Any]:
    """Convert all parsed pieces to the v2.0 JSON structure and optionally write to disk."""
    vertices, find_or_create = _build_vertex_registry()
    edges: List[Dict] = []
    parts: List[Dict] = []

    for piece in pieces_dict.values():
        part = convert_piece_to_part(piece, find_or_create, edges)
        if part:
            parts.append(part)

    json_structure: Dict[str, Any] = {
        "version":  "2.0",
        "units":    "cm",
        "vertices": vertices,
        "edges":    edges,
        "parts":    parts,
        "stitches": [],
        "seams":    [],
    }

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(json_structure, f, indent=4, ensure_ascii=False)

    return json_structure
