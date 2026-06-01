from typing import Dict, List, Any

import matplotlib.colors as mcolors
import matplotlib.cm as mcm

# Maps seam-type prefix → ordered list of roles for that seam family.
# Each role: {'key': json field name, 'label': UI label shown to user}
SEAM_ROLE_CONFIG: Dict[str, List[Dict[str, str]]] = {
    '1': [{'key': 'side_1', 'label': 'Side 1'}, {'key': 'side_2', 'label': 'Side 2'}],
    '3': [{'key': 'base',   'label': 'Base'},   {'key': 'wrap',   'label': 'Wrap'}],
    '6': [{'key': 'edges',  'label': 'Edges'}],
}
DEFAULT_ROLES: List[Dict[str, str]] = [
    {'key': 'side_1', 'label': 'Side 1'},
    {'key': 'side_2', 'label': 'Side 2'},
]

_PHI = 0.618033988749895  # 1 / golden ratio

def seam_colour(index: int) -> str:
    """Return a hex colour for seam number *index* (0-based).

    Alternates between the Blues and Greys perceptually-uniform colormaps,
    using golden-ratio spacing within each so successive colours are
    maximally separated. Scales to any number of seams without repetition.
    """
    t = (index * _PHI) % 1.0
    if index % 2 == 0:
        rgba = mcm.Blues(0.35 + t * 0.60)   # 0.35–0.95: mid-blue to navy
    else:
        rgba = mcm.Greys(0.30 + t * 0.50)   # 0.30–0.80: charcoal to light grey
    return mcolors.to_hex(rgba)

FABRIC_SIDE_COLOURS: Dict[str, str] = {
    'right': '#B4B4B4',
    'left':  '#DCDCDC',
}
