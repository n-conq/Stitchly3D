import logging
import os
from typing import Dict, Any, List, Optional, Callable

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Button

logger = logging.getLogger(__name__)

_IMAGES_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from model import JsonPieceManager
from config import SEAM_ROLE_CONFIG, DEFAULT_ROLES, seam_colour, FABRIC_SIDE_COLOURS
from ui.base import BasePatternPlotter


class SeamDefinitionPlotter(BasePatternPlotter):
    """Mode 2: Define seams by selecting edges and assigning stitches."""

    BUTTON_W = 0.12
    BUTTON_SPACING = 0.015

    def __init__(self, manager: JsonPieceManager,
                 on_done_callback: Optional[Callable] = None, cols: int = 2):
        super().__init__(manager, cols)

        self.on_done_callback = on_done_callback

        # Workflow state: idle | await_start | await_second | await_end | stitch_selected
        self.workflow_state = 'idle'
        self.seam_image_name: Optional[str] = None
        self.stitch_image_name: Optional[str] = None
        self.seam_allowance: float = 0.0

        self.seam_roles: List[Dict] = []
        self.current_role_idx: int = 0
        self.role_edges: List[List[str]] = []

        self.part_fabric_side: Dict[str, str] = {}

        self.start_vertex: Optional[Dict] = None
        self.start_part_id: Optional[str] = None
        self.direction_vertex: Optional[Dict] = None
        self.preview_edges: List[str] = []

        self.create_ui()

    def create_ui(self):
        if not self.create_plot_grid():
            return
        self.plot_parts()
        self._apply_fabric_colours()
        self.create_controls()
        self.connect_events()
        plt.tight_layout(rect=[0, 0.10, 0.85, 0.99], pad=0.4, h_pad=0.5, w_pad=0.5)
        plt.show()

    def create_controls(self):
        n = 3

        create_ax = plt.axes(self._button_rect(0, n))
        create_ax.set_facecolor('#ADD8E6')
        self.create_seam_button = Button(create_ax, 'Create Seam')
        self.create_seam_button.on_clicked(self.create_seam_handler)

        next_ax = plt.axes(self._button_rect(1, n))
        self.next_button = Button(next_ax, 'Next')
        self.next_button.on_clicked(self.next_handler)

        done_ax = plt.axes(self._button_rect(2, n))
        done_ax.set_facecolor('#90EE90')
        self.done_button = Button(done_ax, 'DONE')
        self.done_button.on_clicked(self.done_handler)

        self.seam_list_ax = self.fig.add_axes([0.862, 0.08, 0.13, 0.88])
        self.seam_list_ax.set_axis_off()
        self.update_seam_list()

        self.fig.text(
            0.5, self.BUTTON_Y + self.BUTTON_H + 0.030,
            "Double-click a part to toggle fabric side — "
            "dark grey = right side facing inside the seam",
            ha='center', fontsize=9, color='#555555',
        )
        self.status_text = self.fig.text(
            0.5, self.BUTTON_Y + self.BUTTON_H + 0.005,
            "Click 'Create Seam' to begin",
            ha='center', fontsize=11, weight='bold'
        )

    def connect_events(self):
        self.fig.canvas.mpl_connect('pick_event', self.on_pick)
        self.fig.canvas.mpl_connect('button_press_event', self.on_double_click)


    def on_double_click(self, event):
        if not event.dblclick:
            return
        if event.inaxes is None or not hasattr(event.inaxes, 'part_id'):
            return
        part_id = event.inaxes.part_id
        current = self.part_fabric_side.get(part_id, 'right')
        self.part_fabric_side[part_id] = 'left' if current == 'right' else 'right'
        self._apply_fabric_colours()
        self.fig.canvas.draw_idle()

    def _apply_fabric_colours(self):
        for part_id, ax in self.part_id_to_ax.items():
            side = self.part_fabric_side.get(part_id, 'right')
            ax.set_facecolor(FABRIC_SIDE_COLOURS[side])


    def update_seam_list(self):
        ax = self.seam_list_ax
        ax.cla()
        ax.set_axis_off()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.text(0.05, 0.97, 'Seams', transform=ax.transAxes,
                fontsize=11, fontweight='bold', va='top')
        seams = self.manager.get_all_seams()
        if not seams:
            ax.text(0.05, 0.90, '(none)', transform=ax.transAxes,
                    fontsize=9, color='grey', va='top')
        else:
            row_h = min(0.07, 0.85 / len(seams))
            for i, seam in enumerate(seams):
                y = 0.90 - i * row_h
                ax.text(0.05, y, seam['id'], transform=ax.transAxes,
                        fontsize=9, color=seam.get('color', '#888888'),
                        va='top', fontweight='bold')


    def refresh_plot(self, edge_color_map=None):
        self.plot_parts(edge_color_map)
        self._apply_fabric_colours()
        self.update_seam_list()
        self.fig.canvas.draw_idle()


    def open_image_picker(self, folder: str, title: str, callback: Callable):
        if not os.path.isdir(folder):
            logger.warning("Folder not found: %s", folder)
            return

        png_files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.png')])
        if not png_files:
            logger.warning("No PNG files found in '%s'", folder)
            return

        n = len(png_files)
        cols = min(4, n)
        rows = (n + cols - 1) // cols

        popup_fig, axes_grid = plt.subplots(rows, cols, figsize=(3 * cols, 3 * rows + 0.5))
        popup_fig.suptitle(title, fontsize=14, fontweight='bold')
        popup_fig.patch.set_facecolor('#f5f5f5')

        flat_axes = [axes_grid] if rows == 1 and cols == 1 \
            else list(np.array(axes_grid).flatten())

        for idx, filename in enumerate(png_files):
            ax = flat_axes[idx]
            label = os.path.splitext(filename)[0]
            img_path = os.path.join(folder, filename)
            if PIL_AVAILABLE:
                try:
                    img = PILImage.open(img_path)
                    ax.imshow(np.array(img))
                except Exception:
                    ax.text(0.5, 0.5, label, ha='center', va='center',
                            fontsize=12, transform=ax.transAxes)
            else:
                ax.text(0.5, 0.5, label, ha='center', va='center',
                        fontsize=12, transform=ax.transAxes)
            ax.set_title(label, fontsize=10, pad=4)
            ax.axis('off')
            ax._picker_label = label

        for idx in range(n, len(flat_axes)):
            flat_axes[idx].set_visible(False)

        plt.tight_layout()

        def on_click(event):
            if event.inaxes is not None and hasattr(event.inaxes, '_picker_label'):
                selected = event.inaxes._picker_label
                plt.close(popup_fig)
                callback(selected)

        popup_fig.canvas.mpl_connect('button_press_event', on_click)
        popup_fig.show()


    def create_seam_handler(self, _event):
        self.open_image_picker(os.path.join(_IMAGES_DIR, 'seam_images'), 'Select Seam Type', self.on_seam_image_selected)

    def on_seam_image_selected(self, image_name: str):
        self.seam_image_name = image_name
        prefix = image_name.split('.')[0]
        self.seam_roles = list(SEAM_ROLE_CONFIG.get(prefix, DEFAULT_ROLES))
        self.current_role_idx = 0
        self.role_edges = [[] for _ in self.seam_roles]
        self.stitch_image_name = None
        self._reset_vertex_state()
        self.workflow_state = 'await_start'
        self.refresh_plot()
        self.update_status()

    def next_handler(self, _event):
        if self.workflow_state == 'await_second':
            print("Click a direction vertex first.")
            return

        if self.workflow_state == 'await_end':
            edge_ids, msg = self._edges_on_path(
                self.start_part_id, self.start_vertex,
                self.direction_vertex, self.direction_vertex
            )
            if edge_ids is None:
                logger.warning("%s", msg)
                return
            self._confirm_role(edge_ids)
            return

        if self.workflow_state == 'await_start':
            current_label = self.seam_roles[self.current_role_idx]['label']
            if not self.role_edges[self.current_role_idx]:
                print(f"Select at least one edge for {current_label} first.")
                return
            self.current_role_idx += 1
            if self.current_role_idx < len(self.seam_roles):
                self.refresh_plot(self.get_edge_color_map())
                self.update_status()
            else:
                self.open_image_picker(os.path.join(_IMAGES_DIR, 'stitch_images'), 'Select Stitch Type',
                                       self.on_stitch_image_selected)

    def on_stitch_image_selected(self, image_name: str):
        self.stitch_image_name = image_name
        # Defer dialog open so we are not inside the stitch-picker's on_click
        # callback when creating the new popup (the closing popup's event loop
        # is still mid-event at that point, which prevents the new window from
        # receiving events).
        _timer = self.fig.canvas.new_timer(interval=50)
        def _open():
            _timer.stop()
            self.open_seam_allowance_dialog(self.on_seam_allowance_set)
        _timer.add_callback(_open)
        _timer.start()

    def open_seam_allowance_dialog(self, callback: Callable):
        """Small popup to enter seam allowance in cm.

        Uses direct canvas events (button_press_event / key_press_event) rather
        than Button / TextBox AxesWidgets, which do not receive events reliably
        when the figure is opened from within another figure's event chain.
        """
        popup_fig = plt.figure(figsize=(4, 2.2))
        popup_fig.patch.set_facecolor('#f5f5f5')
        popup_fig.text(0.5, 0.89, 'Seam Allowance',
                       ha='center', fontsize=13, fontweight='bold')
        popup_fig.text(0.5, 0.76, 'Seam allowance (cm):',
                       ha='center', fontsize=11)

        # Input display box — plain axes, no widget
        ax_input = popup_fig.add_axes([0.15, 0.43, 0.70, 0.23])
        ax_input.set_facecolor('white')
        ax_input.set_xticks([])
        ax_input.set_yticks([])
        for sp in ax_input.spines.values():
            sp.set_linewidth(2)
        ax_input._is_input = True
        disp = ax_input.text(0.5, 0.5, '1.0', ha='center', va='center',
                             fontsize=14, transform=ax_input.transAxes)

        # OK button — plain axes, no widget
        ax_ok = popup_fig.add_axes([0.35, 0.09, 0.30, 0.23])
        ax_ok.set_facecolor('#90EE90')
        ax_ok.set_xticks([])
        ax_ok.set_yticks([])
        ax_ok._is_ok = True
        ax_ok.text(0.5, 0.5, 'OK', ha='center', va='center',
                   fontsize=12, fontweight='bold', transform=ax_ok.transAxes)

        err = popup_fig.text(0.5, 0.02, '', ha='center', color='red', fontsize=8)

        buf = ['1.0']

        def _confirm():
            try:
                val = float(buf[0])
            except ValueError:
                err.set_text('Enter a number (e.g. 1.0)')
                popup_fig.canvas.draw_idle()
                return
            plt.close(popup_fig)
            callback(round(val, 3))

        def on_key(event):
            if event.key == 'enter':
                _confirm()
            elif event.key == 'backspace':
                buf[0] = buf[0][:-1]
                disp.set_text(buf[0])
                popup_fig.canvas.draw_idle()
            elif event.key and len(event.key) == 1 and (
                    event.key.isdigit() or event.key == '.'):
                buf[0] += event.key
                disp.set_text(buf[0])
                popup_fig.canvas.draw_idle()

        def on_click(event):
            if event.inaxes is not None and getattr(event.inaxes, '_is_ok', False):
                _confirm()

        popup_fig.canvas.mpl_connect('key_press_event', on_key)
        popup_fig.canvas.mpl_connect('button_press_event', on_click)
        popup_fig.show()

    def on_seam_allowance_set(self, allowance: float):
        self.seam_allowance = allowance
        self.workflow_state = 'stitch_selected'
        self.update_status()

    def done_handler(self, _event):
        if self.workflow_state == 'stitch_selected':
            seam_count = len(self.manager.get_all_seams())
            seam_id    = f"seam_{seam_count + 1}"
            seam_colour_hex = seam_colour(seam_count)
            stitch_id   = self._ensure_stitch(self.stitch_image_name)

            seam_data = {
                "id": seam_id,
                "color": seam_colour_hex,
                "seamType": self.seam_image_name,
                "stitchId": stitch_id,
                "seamAllowance": self.seam_allowance,
                "sewnEdges": [
                    {
                        "id": eid,
                        "role": self.seam_roles[ri]['key'],
                        "fabricSide": self._get_fabric_side(eid),
                    }
                    for ri, edges in enumerate(self.role_edges)
                    for eid in edges
                ],
            }
            success, message = self.manager.add_seam(seam_data)
            logger.info("%s", message)

            if success:
                self.workflow_state = 'idle'
                self.seam_image_name = None
                self.stitch_image_name = None
                self.seam_allowance = 0.0
                self.seam_roles = []
                self.current_role_idx = 0
                self.role_edges = []
                self._reset_vertex_state()
                self.refresh_plot(self.get_edge_color_map())
                self.update_status()
        else:
            logger.info("✓ Seam definition complete! Total seams: %d",
                        len(self.manager.get_all_seams()))
            if self.on_done_callback:
                plt.close(self.fig)
                self.on_done_callback()


    def _get_fabric_side(self, edge_id: str) -> str:
        if edge_id in self.edge_lines:
            _, part_id = self.edge_lines[edge_id]
            return self.part_fabric_side.get(part_id, 'right')
        return 'right'

    def _reset_vertex_state(self):
        self.start_vertex = None
        self.start_part_id = None
        self.direction_vertex = None
        self.preview_edges = []

    def _ensure_stitch(self, stitch_type: str) -> str:
        for s in self.manager.get_all_stitches():
            if s['stitchType'] == stitch_type:
                return s['id']
        stitch_id = f"stitch_{len(self.manager.get_all_stitches()) + 1}"
        self.manager.add_stitch(stitch_id, stitch_type)
        return stitch_id

    def _confirm_role(self, edge_ids: List[str]):
        self.role_edges[self.current_role_idx].extend(edge_ids)
        self._reset_vertex_state()
        self.workflow_state = 'await_start'
        self.refresh_plot(self.get_edge_color_map())
        self.update_status()


    def get_edge_color_map(self) -> Dict[str, Any]:
        color_map: Dict[str, Any] = {}

        for seam in self.manager.get_all_seams():
            colour = seam.get('color', '#888888')
            for entry in seam.get('sewnEdges', []):
                eid = entry['id']
                if isinstance(color_map.get(eid), list):
                    color_map[eid].append(colour)
                else:
                    color_map[eid] = [colour]

        role_colours = ['red', 'blue', 'green', 'purple', 'brown']
        for ri, edges in enumerate(self.role_edges):
            colour = role_colours[ri % len(role_colours)]
            for edge_id in edges:
                color_map[edge_id] = colour
        for edge_id in self.preview_edges:
            color_map[edge_id] = 'orange'

        return color_map


    def on_pick(self, event):
        artist = event.artist
        if not hasattr(artist, 'vertex'):
            return

        vtx     = artist.vertex
        part_id = artist.part_id

        if self.workflow_state == 'await_start':
            self.start_vertex   = vtx
            self.start_part_id  = part_id
            self.direction_vertex = None
            self.preview_edges  = []
            self.workflow_state = 'await_second'

        elif self.workflow_state == 'await_second':
            if part_id != self.start_part_id:
                print("Select a vertex on the same part.")
                return
            path    = self._vertex_path(part_id)
            n       = len(path)
            start_i = self._find_vertex_index(path, self.start_vertex)
            dir_i   = self._find_vertex_index(path, vtx)

            if start_i is not None and dir_i is not None:
                if dir_i not in ((start_i + 1) % n, (start_i - 1) % n):
                    print("Second vertex must be adjacent to the start vertex.")
                    return
                self.direction_vertex = vtx
                edge_ids, _ = self._edges_on_path(part_id, self.start_vertex, vtx, vtx)
                self.preview_edges  = edge_ids or []
                self.workflow_state = 'await_end'
            else:
                edge_id = self._find_edge_between(part_id, self.start_vertex, vtx)
                if edge_id is None:
                    logger.warning("No edge found directly connecting these two vertices.")
                    return
                self.direction_vertex = vtx
                self.preview_edges = [edge_id]
                self.workflow_state = 'await_end'

        elif self.workflow_state == 'await_end':
            if part_id != self.start_part_id:
                print("Select a vertex on the same part.")
                return
            edge_ids, msg = self._edges_on_path(
                part_id, self.start_vertex, self.direction_vertex, vtx
            )
            if edge_ids is None:
                logger.warning("%s", msg)
                return
            self._confirm_role(edge_ids)
            return

        else:
            return

        self.refresh_plot(self.get_edge_color_map())
        self.update_status()


    def update_status(self):
        prefix = f"Seam: {self.seam_image_name}  |  " if self.seam_image_name else ""
        np_ = len(self.preview_edges)

        if self.workflow_state == 'idle':
            msg = "Click 'Create Seam' to begin"

        elif self.workflow_state in ('await_start', 'await_second', 'await_end'):
            if not self.seam_roles:
                msg = ""
            else:
                role  = self.seam_roles[self.current_role_idx]
                label = role['label']
                done_parts = [
                    f"{self.seam_roles[i]['label']}: {len(self.role_edges[i])}"
                    for i in range(self.current_role_idx) if self.role_edges[i]
                ]
                done_str  = ("  |  ".join(done_parts) + "  |  ") if done_parts else ""
                n_cur     = len(self.role_edges[self.current_role_idx])
                is_last   = self.current_role_idx == len(self.seam_roles) - 1
                next_hint = ("open stitch picker" if is_last
                             else f"go to {self.seam_roles[self.current_role_idx + 1]['label']}")

                if self.workflow_state == 'await_start':
                    if n_cur == 0:
                        msg = f"{prefix}{done_str}{label}: Click the START vertex"
                    else:
                        msg = (f"{prefix}{done_str}{label}: {n_cur} edge(s) — "
                               f"click START for more, or 'Next' to {next_hint}")
                elif self.workflow_state == 'await_second':
                    msg = f"{prefix}{done_str}{label}: Click an ADJACENT vertex to set direction"
                else:
                    msg = (f"{prefix}{done_str}{label}: {np_} edge(s) previewed — "
                           f"click END vertex or 'Next' to confirm single edge")

        elif self.workflow_state == 'stitch_selected':
            parts = "  |  ".join(
                f"{self.seam_roles[i]['label']}: {len(self.role_edges[i])} edge(s)"
                for i in range(len(self.seam_roles))
            )
            msg = (f"{prefix}{parts}  |  Stitch: {self.stitch_image_name}  |  "
                   f"Allowance: {self.seam_allowance}cm  |  Click 'DONE' to save")

        else:
            msg = ""

        self.status_text.set_text(msg)
        self.fig.canvas.draw()
