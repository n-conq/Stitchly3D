import logging
from typing import Dict, List, Optional, Callable

import matplotlib.pyplot as plt
from matplotlib.widgets import Button

logger = logging.getLogger(__name__)

from model import JsonPieceManager
from ui.base import BasePatternPlotter


class PartEditPlotter(BasePatternPlotter):
    """Mode 1: Edit parts (copy, mirror, delete, add edges)."""

    def __init__(self, manager: JsonPieceManager,
                 on_done_callback: Optional[Callable] = None, cols: int = 2):
        super().__init__(manager, cols)

        self.on_done_callback = on_done_callback
        self.selected_ax = None

        self.add_edge_mode = False
        self.first_vertex = None
        self.second_vertex = None
        self.first_vertex_artist = None

        # Vertex-based edge selection state machine
        # States: idle | await_start | await_second | await_end | await_mirror_axis
        # | await_line_click
        self.workflow_state = 'idle'
        self.pending_operation: Optional[str] = None  # 'mirror_v'|'mirror_h'|'delete'
        self.selected_edges: List[str] = []
        self.start_vertex: Optional[Dict] = None
        self.start_part_id: Optional[str] = None
        self.direction_vertex: Optional[Dict] = None
        self.preview_edges: List[str] = []

        self.create_ui()

    def create_ui(self):
        if not self.create_plot_grid():
            return
        self.plot_parts()
        self.create_buttons()
        self.connect_events()
        plt.tight_layout(rect=[0, 0.07, 1, 0.99], pad=0.4, h_pad=0.5, w_pad=0.5)
        plt.show()

    def create_buttons(self):
        n = 11
        btn_specs = [
            ('Copy',      self.copy_part_handler),
            ('Mirror V',  self.mirror_vertical_handler),
            ('Mirror H',  self.mirror_horizontal_handler),
            ('Mir Edge V',self.mirror_edge_vertical_handler),
            ('Mir Edge H',self.mirror_edge_horizontal_handler),
            ('Del Edge V',self.delete_edge_handler),
            ('Del Edge L',self.delete_edge_line_handler),
            ('Del Part',  self.delete_part_handler),
            ('Add Edge',  self.toggle_add_edge_mode),
            ('Next',      self.next_handler),
        ]
        self.buttons = {}
        for i, (label, handler) in enumerate(btn_specs):
            ax = plt.axes(self._button_rect(i, n))
            btn = Button(ax, label)
            btn.on_clicked(handler)
            self.buttons[label] = btn

        done_ax = plt.axes(self._button_rect(10, n))
        done_ax.set_facecolor('#90EE90')
        self.done_button = Button(done_ax, 'DONE')
        self.done_button.on_clicked(self.done_handler)

        # Keep a reference for label mutation in add-edge mode
        self.add_edge_button = self.buttons['Add Edge']

        self.status_text = self.fig.text(
            0.5, self.BUTTON_Y + self.BUTTON_H + 0.005,
            '', ha='center', fontsize=10, weight='bold'
        )
        self.update_status()

    def connect_events(self):
        self.fig.canvas.mpl_connect('button_press_event', self.on_click)
        self.fig.canvas.mpl_connect('pick_event', self.on_pick)

    def _rebuild_plot(self):
        self.selected_ax = None
        self._reset_edge_state()
        self.create_plot_grid()
        self.plot_parts()
        self.create_buttons()
        self.connect_events()
        plt.tight_layout(rect=[0, 0.07, 1, 0.99], pad=0.4, h_pad=0.5, w_pad=0.5)
        self.fig.canvas.draw()


    def update_status(self):
        if not hasattr(self, 'status_text'):
            return
        op_labels = {
            'mirror_v': 'Mir Edge V', 'mirror_h': 'Mir Edge H',
            'delete': 'Del Edge V',   'delete_line': 'Del Edge L',
        }
        op  = op_labels.get(self.pending_operation, '')
        np_ = len(self.preview_edges)

        if self.workflow_state == 'idle':
            msg = ''
        elif self.workflow_state == 'await_line_click':
            msg = 'Del Edge L: Click an edge line to delete it'
        elif self.workflow_state == 'await_start':
            msg = f'{op}: Click the START vertex'
        elif self.workflow_state == 'await_second':
            msg = f'{op}: Click an ADJACENT vertex to set direction'
        elif self.workflow_state == 'await_end':
            msg = (f'{op}: {np_} edge(s) previewed — '
                   f'click END vertex or Next to confirm single edge')
        elif self.workflow_state == 'await_mirror_axis':
            axis = 'vertical (x)' if self.pending_operation == 'mirror_v' else 'horizontal (y)'
            msg = (f'{op}: {len(self.selected_edges)} edge(s) selected — '
                   f'click a vertex for the {axis} mirror axis')
        else:
            msg = ''

        self.status_text.set_text(msg)
        self.fig.canvas.draw_idle()


    def _get_edge_color_map(self) -> Dict[str, str]:
        color_map = {}
        for eid in self.selected_edges:
            color_map[eid] = 'green'
        for eid in self.preview_edges:
            color_map[eid] = 'orange'
        return color_map

    def _reset_edge_state(self):
        self.workflow_state = 'idle'
        self.pending_operation = None
        self.selected_edges = []
        self.start_vertex = None
        self.start_part_id = None
        self.direction_vertex = None
        self.preview_edges = []

    def _confirm_edges(self, edge_ids: List[str]):
        self.selected_edges.extend(edge_ids)
        self.start_vertex = None
        self.start_part_id = None
        self.direction_vertex = None
        self.preview_edges = []

        if self.pending_operation == 'delete':
            self._execute_operation()
        elif self.pending_operation in ('mirror_v', 'mirror_h'):
            self.workflow_state = 'await_mirror_axis'
            self.refresh_plot(self._get_edge_color_map())
            self.update_status()

    def _execute_operation(self, axis_vtx: Optional[Dict] = None):
        if self.pending_operation == 'delete':
            for eid in self.selected_edges:
                if eid in self.edge_lines:
                    _, part_id = self.edge_lines[eid]
                    _, message = self.manager.delete_edge(part_id, eid)
                    logger.info("%s", message)
            self._reset_edge_state()
            self._rebuild_plot()

        elif self.pending_operation in ('mirror_v', 'mirror_h') and axis_vtx is not None:
            axis = 'vertical' if self.pending_operation == 'mirror_v' else 'horizontal'
            axis_value = axis_vtx['x'] if axis == 'vertical' else axis_vtx['y']
            for eid in self.selected_edges:
                _, message = self.manager.mirror_edge(eid, axis, axis_value)
                logger.info("%s", message)
            self._reset_edge_state()
            self._rebuild_plot()


    def on_click(self, event):
        if event.inaxes in self.axes and hasattr(event.inaxes, 'part_id'):
            if hasattr(event, 'artist'):
                return
            if self.selected_ax is not None:
                for spine in self.selected_ax.spines.values():
                    spine.set_edgecolor('black')
                    spine.set_linewidth(1)
            self.selected_ax = event.inaxes
            self.manager.select_part(event.inaxes.part_id)
            for spine in self.selected_ax.spines.values():
                spine.set_edgecolor('blue')
                spine.set_linewidth(3)
            self.fig.canvas.draw()
            logger.info("Selected part: %s", event.inaxes.part_id)

    def on_pick(self, event):
        artist = event.artist

        if self.add_edge_mode and hasattr(artist, 'vertex'):
            self.handle_vertex_click(artist)
            return

        if self.pending_operation == 'delete_line' and hasattr(artist, 'edge_id'):
            _, message = self.manager.delete_edge(artist.part_id, artist.edge_id)
            logger.info("%s", message)
            self._reset_edge_state()
            self._rebuild_plot()
            return

        if not hasattr(artist, 'vertex'):
            return

        vtx     = artist.vertex
        part_id = artist.part_id

        if self.workflow_state == 'await_mirror_axis':
            self._execute_operation(axis_vtx=vtx)
            return

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
                    print("Second vertex must be adjacent to the start vertex.")
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
            self._confirm_edges(edge_ids)
            return

        else:
            return

        self.refresh_plot(self._get_edge_color_map())
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
            self._confirm_edges(edge_ids)
            return

        if self.workflow_state == 'await_start':
            if not self.selected_edges:
                print("Select at least one edge first.")
                return
            if self.pending_operation == 'delete':
                self._execute_operation()
            else:
                self.workflow_state = 'await_mirror_axis'
                self.refresh_plot(self._get_edge_color_map())
                self.update_status()


    def toggle_add_edge_mode(self, _event):
        self.add_edge_mode = not self.add_edge_mode
        self.reset_add_edge_state()
        if self.add_edge_mode:
            logger.info("=== ADD EDGE MODE: click two vertices to create an edge ===")
            self.add_edge_button.label.set_text('Exit Add')
        else:
            logger.info("=== ADD EDGE MODE DEACTIVATED ===")
            self.add_edge_button.label.set_text('Add Edge')
        self.fig.canvas.draw()

    def handle_vertex_click(self, artist):
        if self.first_vertex is None:
            self.first_vertex = artist.vertex
            self.first_vertex_artist = artist
            artist.set_color('blue')
            artist.set_markersize(8)
            self.fig.canvas.draw()
            logger.info("First vertex: (%s, %s)", artist.vertex['x'], artist.vertex['y'])
            print("Click second vertex...")
        else:
            self.second_vertex = artist.vertex
            success, message = self.manager.add_edge(
                artist.part_id, self.first_vertex, self.second_vertex
            )
            logger.info("%s", message)
            if success:
                self.reset_add_edge_state()
                self._rebuild_plot()

    def reset_add_edge_state(self):
        if self.first_vertex_artist is not None:
            self.first_vertex_artist.set_color('red')
            self.first_vertex_artist.set_markersize(5)
        self.first_vertex = None
        self.second_vertex = None
        self.first_vertex_artist = None
        if hasattr(self, 'fig'):
            self.fig.canvas.draw()


    def copy_part_handler(self, _event):
        success, message = self.manager.copy_selected_part()
        logger.info("%s", message)
        if success:
            self._rebuild_plot()

    def mirror_vertical_handler(self, _event):
        success, message = self.manager.mirror_selected_part(axis='vertical')
        logger.info("%s", message)
        if success:
            self._rebuild_plot()

    def mirror_horizontal_handler(self, _event):
        success, message = self.manager.mirror_selected_part(axis='horizontal')
        logger.info("%s", message)
        if success:
            self._rebuild_plot()

    def mirror_edge_vertical_handler(self, _event):
        self._reset_edge_state()
        self.pending_operation = 'mirror_v'
        self.workflow_state    = 'await_start'
        self.update_status()

    def mirror_edge_horizontal_handler(self, _event):
        self._reset_edge_state()
        self.pending_operation = 'mirror_h'
        self.workflow_state    = 'await_start'
        self.update_status()

    def delete_edge_handler(self, _event):
        self._reset_edge_state()
        self.pending_operation = 'delete'
        self.workflow_state    = 'await_start'
        self.update_status()

    def delete_edge_line_handler(self, _event):
        self._reset_edge_state()
        self.pending_operation = 'delete_line'
        self.workflow_state    = 'await_line_click'
        self.update_status()

    def delete_part_handler(self, _event):
        success, message = self.manager.delete_selected_part()
        logger.info("%s", message)
        if success:
            self._rebuild_plot()

    def done_handler(self, _event):
        logger.info("✓ Part editing complete!")
        if self.on_done_callback:
            plt.close(self.fig)
            self.on_done_callback()
