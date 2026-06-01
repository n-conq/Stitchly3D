# Stitchly3D — Cutting Pattern Processing Tool

Stitchly3D converts parametric sewing pattern files from Seamly2D into a
structured JSON format that encodes seam topology for use in 3D garment
simulation pipelines. It provides a two-stage interactive editor for
refining pattern pieces and assigning seam and stitch types.

## Scope

The tool produces **structural seam topology** — which edges are sewn
together, in what order, and with which stitch type. It does not produce
seam allowances, notch positions, or production-ready cut files. These
are planned for future work; the current output is intended as input to
3D simulation software (VStitcher, CLO3D) or downstream research pipelines.

---

## Requirements

- **Python** 3.10 or later (developed and tested on Python 3.13)
- **Operating system**: Windows, macOS, and Linux. The `Ctrl+V` clipboard
  shortcut in the file-selection dialog uses `pbpaste` on macOS and `xsel`
  on Linux; if neither is installed the shortcut silently does nothing while
  all other functionality remains available.

### Python dependencies

```
matplotlib==3.10.8
numpy==2.4.1
jsonschema==4.26.0
```

**Optional:** `Pillow==12.1.0` — enables PNG thumbnail display in the seam
and stitch type picker dialogs. Without it the picker shows text labels only
and all other functionality is unaffected.

Install all dependencies including Pillow:

```
pip install -r requirements.txt
```

---

## Installation

```
git clone <repository-url>
cd Stitchly3D
pip install -r requirements.txt
```

No package installation step is required. Run directly from the
`Stitchly3D/` directory.

---

## Usage

```
python app.py
```

A file-selection dialog appears. Enter (or paste with `Ctrl+V` on Windows)
the paths to:

1. A Seamly2D pattern file (`.sm2d`)
2. A Seamly2D measurements file (`.smis`)

The tool then runs two interactive stages in sequence.

### Stage 1 — Part editor

Each pattern piece is shown in its own subplot. Available actions:

| Action | How |
|---|---|
| Add edge | Click two vertices on a part |
| Mirror edge | Select an edge, choose axis and value, click Mirror |
| Delete edge | Select an edge, click Delete |
| Copy part | Select a part subplot, click Copy |
| Mirror part | Select a part subplot, choose axis, click Mirror Part |
| Done | Click DONE to proceed to Stage 2 |

### Stage 2 — Seam definition editor

Select edges across parts to define seam pairs.

**3-click edge range selection** (the core interaction):
1. Click the **start vertex** of the range
2. Click the **direction vertex** (the adjacent vertex that sets traversal direction)
3. Click the **end vertex**

The selected edge range is highlighted. Then choose a seam type, stitch
type, and fabric side, and click Assign Seam.

This vertex-first model is deliberate: it is unambiguous at small edge
lengths where clicking the edge line itself is imprecise.

---

## Worked example

A hat pattern is included as a complete worked example.

**Input**: `../Stitchly3D\cutting_pattern_Hat.json`
(already converted from `.sm2d`; load directly via `PatternEditorApp`)

**Direct load** (bypassing the file-selection dialog):

```python
from app import PatternEditorApp
PatternEditorApp('../Stitchly3D\cutting_pattern_Hat.json')
```

The file contains 44 edges across 1 part, stored in v2.0 format with a
global vertex table (no coordinate duplication). After defining seams and
clicking DONE, the updated JSON is written back to the same file.

---

## Output format

Output is a JSON file conforming to `schema-cutting-pattern.json`
(JSON Schema 2020-12). Top-level structure:

```json
{
  "version": "2.0",
  "units": "cm",
  "vertices": [ { "id": "v_1", "x": 28.79, "y": 1.06 }, ... ],
  "edges":    [ { "id": "e_1", "v1": "v_1", "v2": "v_2", "type": "outline" }, ... ],
  "parts":    [ { "id": "part_hat", "edgeIds": ["e_1", ...] } ],
  "stitches": [ { "id": "stitch_1", "stitchType": "..." } ],
  "seams":    [ { "id": "seam_1", "color": "#e6194b", "seamType": "...",
                  "stitchId": "stitch_1", "sewnEdges": [...] } ]
}
```

All coordinate values are in **centimetres**. Edge `type` is one of
`"outline"` (closed boundary), `"mirror"` (reflected fold/seam line), or
`"construction"` (manually added interior line).

---

## Running the tests

```
pytest tests/ -v
```

The test suite covers all pure geometric functions in `geometry.py` (43 tests,
no GUI or file I/O required).

---

## Known limitations

- **No seam allowance**: edges represent finished-seam lines. Seam allowance
  width and corner treatment are out of scope for this version.
- **No DXF / SVG export**: output is JSON only.
- **Grain line not visualised**: `grainlineRotation` is stored per-part but
  not displayed in the editor.
- **Seam/stitch type vocabulary**: types are stored as image filenames from
  the `seam_images/` folder. The valid vocabulary is implicit in the folder
  contents rather than in an enumerated schema.
- **Clipboard paste** (`Ctrl+V` in the file dialog) requires `xsel` on Linux;
  on Windows and macOS it works out of the box.
- **matplotlib UI**: the editor uses matplotlib's event system. Zoom/pan
  may conflict with vertex picking. A Qt-based canvas is planned for the
  integrated version.
