import logging
from typing import Dict, Any, List, Tuple, Optional

import numpy as np
import matplotlib.pyplot as plt

from model import JsonPieceManager
from geometry import (
    outline_edges, vertex_path, find_vertex_index,
    find_edge_between, edges_on_path, walk_to_vertex,
    rotate_edges_for_display,
)

logger = logging.getLogger(__name__)


class BasePatternPlotter:
    """Shared plotting infrastructure for both editor modes."""

    BUTTON_W = 0.08
    BUTTON_H = 0.04
    BUTTON_Y = 0.02
    BUTTON_SPACING = 0.009

    def __init__(self, manager: JsonPieceManager, cols: int = 2):
        self.manager = manager
        self.cols = cols
        self.fig = None
        self.axes = None
        self.part_id_to_ax: Dict[str, Any] = {}
        self.edge_lines: Dict[str, Tuple] = {}
        self.vertex_artists: Dict[str, Any] = {}

    def _button_rect(self, index: int, n_buttons: int) -> list:
        """Return [x, y, w, h] for button at position *index* in a row of *n_buttons*."""
        total_width = n_buttons * self.BUTTON_W + (n_buttons - 1) * self.BUTTON_SPACING
        start_x = (1 - total_width) / 2
        x = start_x + index * (self.BUTTON_W + self.BUTTON_SPACING)
        return [x, self.BUTTON_Y, self.BUTTON_W, self.BUTTON_H]

    def create_plot_grid(self) -> bool:
        """Create the subplot grid, reusing the existing window on redraws."""
        parts = self.manager.get_all_parts()
        if not parts:
            logger.warning("No parts found in JSON file!")
            return False

        n_parts = len(parts)
        actual_cols = min(self.cols, n_parts)
        rows = (n_parts + actual_cols - 1) // actual_cols

        if self.fig is None:
            self.fig, self.axes = plt.subplots(rows, actual_cols,
                                               figsize=(12, 6 * rows + 1))
            try:
                fig_manager = plt.get_current_fig_manager()
                if hasattr(fig_manager, 'window'):
                    fig_manager.window.showMaximized()
            except Exception:
                pass
        else:
            self.fig.clf()
            self.axes = self.fig.subplots(rows, actual_cols)

        if rows == 1 and actual_cols == 1:
            self.axes = [self.axes]
        else:
            self.axes = np.array(self.axes).flatten()

        return True


    def plot_parts(self, edge_color_map: Optional[Dict[str, Any]] = None):
        """Draw all parts on the subplot grid."""
        parts = self.manager.get_all_parts()
        self.edge_lines = {}
        self.vertex_artists = {}
        self.part_id_to_ax = {}

        for idx, part in enumerate(parts):
            if idx >= len(self.axes):
                break

            ax = self.axes[idx]
            ax.clear()
            part_id = part['id']
            self.part_id_to_ax[part_id] = ax

            resolved_edges = self.manager.get_part_edges(part_id)
            if resolved_edges:
                try:
                    grain_rot = float(part.get('grainlineRotation') or 0)
                except (ValueError, TypeError):
                    grain_rot = 0.0
                display_edges = rotate_edges_for_display(
                    resolved_edges, 90.0 - grain_rot
                )

                # Build vertex maps: display positions for plotting,
                # original coords kept in artist.vertex for model operations.
                orig_verts: Dict[str, Any] = {}
                disp_verts: Dict[str, Any] = {}
                for re, de in zip(resolved_edges, display_edges):
                    for vd in (re['vertex1'], re['vertex2']):
                        if vd['id'] not in orig_verts:
                            orig_verts[vd['id']] = vd
                    for vd in (de['vertex1'], de['vertex2']):
                        if vd['id'] not in disp_verts:
                            disp_verts[vd['id']] = vd

                for edge, disp_edge in zip(resolved_edges, display_edges):
                    edge_id = edge['id']
                    v1, v2 = disp_edge['vertex1'], disp_edge['vertex2']
                    xs = [v1['x'], v2['x']]
                    ys = [v1['y'], v2['y']]

                    raw = edge_color_map.get(edge_id) if edge_color_map else None
                    if raw is None:
                        colours = ['black']
                    elif isinstance(raw, list):
                        colours = raw
                    else:
                        colours = [raw]

                    if len(colours) == 1:
                        line, = ax.plot(xs, ys, '-', color=colours[0],
                                        linewidth=2, picker=5)
                        line.edge_id = edge_id
                        line.part_id = part_id
                        self.edge_lines[edge_id] = (line, part_id)
                    else:
                        dash = 6
                        gap = dash * (len(colours) - 1)
                        for ci, colour in enumerate(colours):
                            ln, = ax.plot(xs, ys, color=colour, linewidth=2,
                                          picker=5 if ci == 0 else False)
                            ln.set_linestyle((ci * dash, (dash, gap)))
                            if ci == 0:
                                ln.edge_id = edge_id
                                ln.part_id = part_id
                                self.edge_lines[edge_id] = (ln, part_id)

                for vid, disp_vertex in disp_verts.items():
                    artist, = ax.plot([disp_vertex['x']], [disp_vertex['y']],
                                      'o', color='red', markersize=5,
                                      alpha=0.7, picker=10)
                    artist.vertex = orig_verts[vid]
                    artist.part_id = part_id
                    self.vertex_artists[vid] = artist

            ax.set_xlabel('X (cm)', fontsize=11)
            ax.set_ylabel('Y (cm)', fontsize=11)
            title = part_id.replace('part_', '').replace('_', ' ').title()
            ax.set_title(title, fontsize=13, fontweight='bold')
            ax.grid(True, alpha=0.3)
            ax.set_aspect('equal')
            ax.set_picker(True)
            ax.part_id = part_id

        for idx in range(len(parts), len(self.axes)):
            self.axes[idx].set_visible(False)

    def refresh_plot(self, edge_color_map: Optional[Dict[str, Any]] = None):
        """Refresh the plot without closing the window."""
        self.plot_parts(edge_color_map)
        self.fig.canvas.draw_idle()

    def _get_part_edges(self, part_id: str) -> List[Dict]:
        return self.manager.get_part_edges(part_id)

    def _outline_edges(self, part_id: str) -> List[Dict]:
        return outline_edges(self._get_part_edges(part_id))

    def _vertex_path(self, part_id: str) -> List[Tuple[float, float]]:
        return vertex_path(self._get_part_edges(part_id))

    def _find_vertex_index(self, path: List[Tuple[float, float]],
                           vtx: Dict) -> Optional[int]:
        return find_vertex_index(path, vtx)

    def _find_edge_between(self, part_id: str, v1: Dict, v2: Dict) -> Optional[str]:
        return find_edge_between(self._get_part_edges(part_id), v1, v2)

    def _edges_on_path(self, part_id: str, start_vtx: Dict, dir_vtx: Dict,
                       end_vtx: Dict) -> Tuple[Optional[List[str]], str]:
        return edges_on_path(self._get_part_edges(part_id), start_vtx, dir_vtx, end_vtx)

    def _walk_to_vertex(self, part_id: str, start_vtx: Dict, dir_vtx: Dict,
                        end_vtx: Dict) -> Tuple[Optional[List[str]], str]:
        return walk_to_vertex(self._get_part_edges(part_id), start_vtx, dir_vtx, end_vtx)
