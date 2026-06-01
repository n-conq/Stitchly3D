"""
Test suite for geometry.py — pure geometric functions.

Run from the Stitchly3D/ directory:
    pytest tests/ -v

No matplotlib, no file I/O, no plotters needed.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from geometry import (
    outline_edges,
    vertex_path,
    find_vertex_index,
    find_edge_between,
    edges_on_path,
    walk_to_vertex,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _vid(x, y) -> str:
    """Deterministic vertex ID from coordinates — used in test fixtures."""
    return f"{float(x)},{float(y)}"


def edge(id, x1, y1, x2, y2, edge_type='outline'):
    e = {
        "id": id,
        "vertex1": {"id": _vid(x1, y1), "x": float(x1), "y": float(y1)},
        "vertex2": {"id": _vid(x2, y2), "x": float(x2), "y": float(y2)},
    }
    if edge_type != 'outline':
        e["type"] = edge_type
    return e


def v(x, y):
    return {"id": _vid(x, y), "x": float(x), "y": float(y)}


def square():
    """Clean 4-edge square: (0,0)→(1,0)→(1,1)→(0,1)→(0,0)."""
    return [
        edge("e1", 0, 0, 1, 0),
        edge("e2", 1, 0, 1, 1),
        edge("e3", 1, 1, 0, 1),
        edge("e4", 0, 1, 0, 0),
    ]


def triangle():
    """3-edge triangle: (0,0)→(2,0)→(1,2)→(0,0)."""
    return [
        edge("e1", 0, 0, 2, 0),
        edge("e2", 2, 0, 1, 2),
        edge("e3", 1, 2, 0, 0),
    ]


# ===========================================================================
# outline_edges
# ===========================================================================

class TestOutlineEdges:
    def test_excludes_standalone(self):
        edges = [edge("e1", 0, 0, 1, 0), edge("s1", 0, 0, 0, 1, edge_type='construction')]
        result = outline_edges(edges)
        assert [e["id"] for e in result] == ["e1"]

    def test_includes_all_when_no_standalone(self):
        assert len(outline_edges(square())) == 4

    def test_empty_input(self):
        assert outline_edges([]) == []

    def test_all_standalone_returns_empty(self):
        edges = [edge("s1", 0, 0, 1, 0, edge_type='construction')]
        assert outline_edges(edges) == []


# ===========================================================================
# vertex_path
# ===========================================================================

class TestVertexPath:
    def test_square_path(self):
        path = vertex_path(square())
        assert path == [_vid(0,0), _vid(1,0), _vid(1,1), _vid(0,1)]

    def test_triangle_path(self):
        path = vertex_path(triangle())
        assert path == [_vid(0,0), _vid(2,0), _vid(1,2)]

    def test_standalone_excluded_from_path(self):
        edges = square() + [edge("s1", 0.5, 0, 0.5, 0.5, edge_type='construction')]
        path = vertex_path(edges)
        assert len(path) == 4
        assert _vid(0.5, 0.0) not in path

    def test_no_closing_duplicate(self):
        # path[0] and path[-1] are vertex IDs of different vertices.
        path = vertex_path(square())
        assert path[0] != path[-1]

    def test_empty_returns_empty(self):
        assert vertex_path([]) == []


# ===========================================================================
# find_vertex_index
# ===========================================================================

class TestFindVertexIndex:
    def test_finds_first_vertex(self):
        path = [_vid(0,0), _vid(1,0), _vid(1,1)]
        assert find_vertex_index(path, v(0, 0)) == 0

    def test_finds_middle_vertex(self):
        path = [_vid(0,0), _vid(1,0), _vid(1,1)]
        assert find_vertex_index(path, v(1, 0)) == 1

    def test_finds_last_vertex(self):
        path = [_vid(0,0), _vid(1,0), _vid(1,1)]
        assert find_vertex_index(path, v(1, 1)) == 2

    def test_returns_none_when_not_found(self):
        path = [_vid(0,0), _vid(1,0)]
        assert find_vertex_index(path, v(5, 5)) is None

    def test_empty_path_returns_none(self):
        assert find_vertex_index([], v(0, 0)) is None


# ===========================================================================
# find_edge_between
# ===========================================================================

class TestFindEdgeBetween:
    def test_forward_direction(self):
        edges = [edge("e1", 0, 0, 1, 0)]
        assert find_edge_between(edges, v(0, 0), v(1, 0)) == "e1"

    def test_reverse_direction(self):
        edges = [edge("e1", 0, 0, 1, 0)]
        assert find_edge_between(edges, v(1, 0), v(0, 0)) == "e1"

    def test_returns_none_when_no_connection(self):
        edges = [edge("e1", 0, 0, 1, 0)]
        assert find_edge_between(edges, v(0, 0), v(2, 0)) is None

    def test_finds_among_multiple_edges(self):
        edges = square()
        assert find_edge_between(edges, v(1, 0), v(1, 1)) == "e2"

    def test_empty_edges_returns_none(self):
        assert find_edge_between([], v(0, 0), v(1, 0)) is None

    def test_standalone_edge_also_found(self):
        edges = [edge("s1", 2, 2, 3, 3, edge_type='construction')]
        assert find_edge_between(edges, v(2, 2), v(3, 3)) == "s1"


# ===========================================================================
# edges_on_path — standard convex polygon (square)
# ===========================================================================

class TestEdgesOnPathConvex:
    def test_forward_single_edge(self):
        result, _ = edges_on_path(square(), v(0, 0), v(1, 0), v(1, 0))
        assert result == ["e1"]

    def test_forward_two_edges(self):
        result, _ = edges_on_path(square(), v(0, 0), v(1, 0), v(1, 1))
        assert result == ["e1", "e2"]

    def test_forward_three_edges(self):
        result, _ = edges_on_path(square(), v(0, 0), v(1, 0), v(0, 1))
        assert result == ["e1", "e2", "e3"]

    def test_backward_single_edge(self):
        # Going backward from (0,0): the preceding edge is e4 (0,1)→(0,0)
        result, _ = edges_on_path(square(), v(0, 0), v(0, 1), v(0, 1))
        assert result == ["e4"]

    def test_backward_two_edges(self):
        result, _ = edges_on_path(square(), v(0, 0), v(0, 1), v(1, 1))
        assert result == ["e4", "e3"]

    def test_backward_three_edges(self):
        result, _ = edges_on_path(square(), v(0, 0), v(0, 1), v(1, 0))
        assert result == ["e4", "e3", "e2"]

    def test_same_start_and_end_returns_error(self):
        result, _ = edges_on_path(square(), v(0, 0), v(1, 0), v(0, 0))
        assert result is None

    def test_non_adjacent_direction_returns_error(self):
        # (1,1) is not adjacent to (0,0) on the square
        result, _ = edges_on_path(square(), v(0, 0), v(1, 1), v(1, 0))
        assert result is None


# ===========================================================================
# edges_on_path — wrap-around (backward past index 0)
# ===========================================================================

class TestEdgesOnPathWrapAround:
    def test_backward_wrap_from_index_zero(self):
        result, _ = edges_on_path(square(), v(0, 0), v(0, 1), v(1, 0))
        assert result == ["e4", "e3", "e2"]

    def test_forward_wrap_full_polygon_minus_one(self):
        result, _ = edges_on_path(square(), v(0, 0), v(1, 0), v(0, 1))
        assert result == ["e1", "e2", "e3"]


# ===========================================================================
# edges_on_path — concave polygon with re-entrant vertex
# ===========================================================================

class TestEdgesOnPathConcave:
    def concave(self):
        # L-shape: (0,0)→(2,0)→(2,1)→(1,1)→(1,2)→(0,2)→(0,0)
        return [
            edge("e1", 0, 0, 2, 0),
            edge("e2", 2, 0, 2, 1),
            edge("e3", 2, 1, 1, 1),  # re-entrant corner at (1,1)
            edge("e4", 1, 1, 1, 2),
            edge("e5", 1, 2, 0, 2),
            edge("e6", 0, 2, 0, 0),
        ]

    def test_forward_through_reentrant_corner(self):
        result, _ = edges_on_path(self.concave(), v(2, 0), v(2, 1), v(1, 1))
        assert result == ["e2", "e3"]

    def test_backward_through_reentrant_corner(self):
        result, _ = edges_on_path(self.concave(), v(1, 1), v(2, 1), v(2, 0))
        assert result == ["e3", "e2"]


# ===========================================================================
# edges_on_path — closing-duplicate-vertex scenario
# ===========================================================================

class TestClosingDuplicateVertex:
    def test_path_has_no_duplicate_after_converter_fix(self):
        # Simulates a raw parser outline where first == last point.
        # The converter strips the closing duplicate before building edges;
        # this test verifies that after stripping, the path is clean.
        outline_x = [0.0, 1.0, 1.0, 0.0, 0.0]  # last == first
        outline_y = [0.0, 0.0, 1.0, 1.0, 0.0]

        if (round(outline_x[-1], 5) == round(outline_x[0], 5) and
                round(outline_y[-1], 5) == round(outline_y[0], 5)):
            outline_x = outline_x[:-1]
            outline_y = outline_y[:-1]

        edges = [
            edge(f"e{i+1}", outline_x[i], outline_y[i],
                 outline_x[(i+1) % len(outline_x)],
                 outline_y[(i+1) % len(outline_x)])
            for i in range(len(outline_x))
        ]

        path = vertex_path(edges)
        assert len(path) == 4
        assert path[0] != path[-1]

    def test_backward_from_origin_works_after_fix(self):
        result, _ = edges_on_path(square(), v(0, 0), v(0, 1), v(0, 1))
        assert result == ["e4"]


# ===========================================================================
# edges_on_path — standalone / mirrored edges
# ===========================================================================

class TestEdgesOnPathStandalone:
    def edges_with_dart(self):
        # Square outline + a dart (standalone V-shape) attached at (0.5, 0)
        return square() + [
            edge("dart1", 0.5, 0,   0.5, 0.5, edge_type='construction'),
            edge("dart2", 0.5, 0.5, 1.5, 0.5, edge_type='construction'),
        ]

    def test_single_standalone_edge_selected(self):
        # start vertex (0.5, 0) is off the outline — falls back to walk_to_vertex
        result, _ = edges_on_path(
            self.edges_with_dart(), v(0.5, 0), v(0.5, 0.5), v(0.5, 0.5)
        )
        assert result == ["dart1"]

    def test_range_across_two_standalone_edges(self):
        result, _ = edges_on_path(
            self.edges_with_dart(), v(0.5, 0), v(0.5, 0.5), v(1.5, 0.5)
        )
        assert result == ["dart1", "dart2"]

    def test_disconnected_standalone_returns_none(self):
        edges = square() + [edge("s1", 5, 5, 6, 5, edge_type='construction')]
        result, _ = edges_on_path(edges, v(0, 0), v(1, 0), v(5, 5))
        assert result is None


# ===========================================================================
# walk_to_vertex
# ===========================================================================

class TestWalkToVertex:
    def test_single_step(self):
        edges = [edge("e1", 0, 0, 1, 0)]
        result, _ = walk_to_vertex(edges, v(0, 0), v(1, 0), v(1, 0))
        assert result == ["e1"]

    def test_two_steps(self):
        edges = [edge("e1", 0, 0, 1, 0), edge("e2", 1, 0, 2, 0)]
        result, _ = walk_to_vertex(edges, v(0, 0), v(1, 0), v(2, 0))
        assert result == ["e1", "e2"]

    def test_direction_not_adjacent_returns_none(self):
        edges = [edge("e1", 0, 0, 1, 0)]
        result, _ = walk_to_vertex(edges, v(0, 0), v(5, 5), v(1, 0))
        assert result is None

    def test_end_unreachable_returns_none(self):
        edges = [edge("e1", 0, 0, 1, 0), edge("e2", 5, 5, 6, 5)]
        result, _ = walk_to_vertex(edges, v(0, 0), v(1, 0), v(5, 5))
        assert result is None

    def test_degenerate_edge_skipped(self):
        # Zero-length edges (v1 == v2) are excluded from the adjacency graph.
        edges = [
            edge("degen", 0, 0, 0, 0),  # zero-length, should be ignored
            edge("e1",    0, 0, 1, 0),
        ]
        result, _ = walk_to_vertex(edges, v(0, 0), v(1, 0), v(1, 0))
        assert result == ["e1"]

    def test_traverses_standalone_and_outline_together(self):
        # Mixed: one outline edge, one standalone, chained
        edges = [
            edge("e1", 0, 0, 1, 0),
            edge("s1", 1, 0, 1, 1, edge_type='mirror'),
        ]
        result, _ = walk_to_vertex(edges, v(0, 0), v(1, 0), v(1, 1))
        assert result == ["e1", "s1"]
