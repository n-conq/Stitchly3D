import logging
import os
import sys
import subprocess

import matplotlib.pyplot as plt

logger = logging.getLogger(__name__)
from matplotlib.widgets import Button, TextBox

from seamly_parser import parse_pattern_file
from converter import pieces_to_json
from model import JsonPieceManager
from ui.part_editor import PartEditPlotter
from ui.seam_editor import SeamDefinitionPlotter


def _get_clipboard_text() -> str:
    """Read plain text from the system clipboard (cross-platform)."""
    try:
        if sys.platform == 'win32':
            cmd = ['powershell', '-noprofile', '-command', 'Get-Clipboard']
        elif sys.platform == 'darwin':
            cmd = ['pbpaste']
        else:
            cmd = ['xsel', '--clipboard', '--output']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        return result.stdout.strip()
    except Exception as exc:
        logger.warning("Clipboard read unavailable: %s", exc)
        return ''


def select_input_files():
    """Show a small matplotlib form to collect pattern and measure file paths."""
    result = {}

    fig, ax = plt.subplots(figsize=(6, 3))
    fig.canvas.manager.set_window_title('Cutting Pattern Tool')
    ax.set_axis_off()

    fig.text(0.5, 0.88, 'Cutting Pattern Tool',
             ha='center', fontsize=14, fontweight='bold')
    fig.text(0.05, 0.68, 'Pattern file (.sm2d):', fontsize=10)
    fig.text(0.05, 0.38, 'Measure file (.smis):', fontsize=10)

    ax_pattern = fig.add_axes([0.05, 0.52, 0.88, 0.10])
    ax_measure  = fig.add_axes([0.05, 0.22, 0.88, 0.10])
    ax_next     = fig.add_axes([0.35, 0.05, 0.30, 0.12])

    tb_pattern = TextBox(ax_pattern, '', initial='')
    tb_measure  = TextBox(ax_measure,  '', initial='')
    btn_next    = Button(ax_next, 'Next')
    ax_next.set_facecolor('#90EE90')

    def on_next(_event):
        p = tb_pattern.text.strip()
        m = tb_measure.text.strip()
        if not os.path.isfile(p):
            fig.text(0.5, 0.01, 'Pattern file not found.', ha='center',
                     color='red', fontsize=9)
            fig.canvas.draw()
            return
        if not os.path.isfile(m):
            fig.text(0.5, 0.01, 'Measure file not found.', ha='center',
                     color='red', fontsize=9)
            fig.canvas.draw()
            return
        result['pattern'] = p
        result['measure'] = m
        plt.close(fig)

    active_tb = [None]

    def on_click(event):
        if event.inaxes == ax_pattern:
            active_tb[0] = tb_pattern
        elif event.inaxes == ax_measure:
            active_tb[0] = tb_measure

    def on_key(event):
        if event.key == 'ctrl+v' and active_tb[0] is not None:
            clip = _get_clipboard_text().strip()
            if clip:
                active_tb[0].set_val(clip)

    btn_next.on_clicked(on_next)
    fig.canvas.mpl_connect('button_press_event', on_click)
    fig.canvas.mpl_connect('key_press_event', on_key)
    fig.canvas.mpl_connect('close_event',
                           lambda _: sys.exit(0) if 'pattern' not in result else None)

    plt.show()
    return result['pattern'], result['measure']


class PatternEditorApp:
    """Coordinator: runs part editing then seam definition in sequence."""

    def __init__(self, json_file: str):
        self.manager = JsonPieceManager(json_file)
        self.current_plotter = None

        print("=" * 60)
        print("PATTERN EDITOR")
        print("=" * 60)

        self.start_edit_mode()

    def start_edit_mode(self):
        print("\n>>> PART EDITING MODE <<<")
        print("Edit your pattern pieces, then click DONE")
        self.current_plotter = PartEditPlotter(
            self.manager,
            on_done_callback=self.start_seam_mode,
        )

    def start_seam_mode(self):
        print("\n>>> SEAM DEFINITION MODE <<<")
        print("Define seams by selecting edges and assigning stitches")
        self.current_plotter = SeamDefinitionPlotter(
            self.manager,
            on_done_callback=self.finish,
        )

    def finish(self):
        print("\n" + "=" * 60)
        print("PATTERN EDITING COMPLETE!")
        print("=" * 60)

        parts    = self.manager.get_all_parts()
        stitches = self.manager.get_all_stitches()
        seams    = self.manager.get_all_seams()

        print(f"\nSummary:")
        print(f"  Parts: {len(parts)}")
        print(f"  Stitches: {len(stitches)}")
        print(f"  Seams: {len(seams)}")
        print(f"\nData saved to: {self.manager.json_file}")

        plt.close('all')


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s %(name)s: %(message)s',
    )
    patternfile, measurefile = select_input_files()
    pieces = parse_pattern_file(patternfile, measurefile)
    output_file = patternfile.replace('.sm2d', '.json')
    json_data = pieces_to_json(pieces, output_file)
    logger.info("Converted %d parts to %s", len(json_data['parts']), output_file)
    logger.info("Total vertices: %d, edges: %d",
                len(json_data['vertices']), len(json_data['edges']))
    PatternEditorApp(output_file)


if __name__ == '__main__':
    main()
