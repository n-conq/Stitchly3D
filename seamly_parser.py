
import logging
import xml.etree.ElementTree as ET
import numpy as np
import math
import re
from typing import Optional
import copy

logger = logging.getLogger(__name__)

try:
    import import_measurements_second as meas
    HAS_MEASUREMENTS = True
except ImportError:
    HAS_MEASUREMENTS = False
    logger.warning("import_measurements_second module not found. Using default measurements.")



class Point:
    def __init__(self, **kwargs):
        # Assign all XML attributes as object attributes
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __repr__(self):
        attrs = ", ".join(f"{k}={v}" for k, v in self.__dict__.items())
        return f"Point({attrs})"
    

class Spline:
    def __init__(self, **kwargs):
        self.points = []  # List of Point objects
        for key, value in kwargs.items():
            setattr(self, key, value)
            
    def add_point(self, point):
        """Add a Point object to the spline."""
        self.points.append(point)

    def __repr__(self):
        return f"Spline(points={len(self.points)})"


class Line:
    def __init__(self, **kwargs):
        self.points = []  # List of Point objects
        for key, value in kwargs.items():
            setattr(self, key, value)
            
    def add_point(self, point):
        """Add a Point object to the line."""
        self.points.append(point)

    def __repr__(self):
        return f"Line(points={len(self.points)})"
    

class Piece:
    def __init__(self, **kwargs):
        self.points = []  # List of Point objects
        self.lines = []   # List of Line objects
        self.splines = [] # List of Spline objects
        
        # Set attributes from kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def add_point(self, point):
        """Add a Point object to the piece."""
        self.points.append(point)
    
    def add_line(self, line):
        """Add a Line object to the piece."""
        self.lines.append(line)
    
    def add_spline(self, spline):
        """Add a Spline object to the piece."""
        self.splines.append(spline)
    
    def __repr__(self):
        return f"Piece(id={getattr(self, 'id', None)}, name={getattr(self, 'name', None)}, points={len(self.points)}, lines={len(self.lines)}, splines={len(self.splines)})"



def load_measurements(measurement_file_path: Optional[str] = None) -> dict:
    """
    Load body measurements from file.
    
    Parameters:
    -----------
    measurement_file_path : str, optional
        Path to the .smis measurement file
        
    Returns:
    --------
    dict : Measurement dictionary
    """
    if measurement_file_path and HAS_MEASUREMENTS:
        try:
            return meas.import_body_measurements(measurement_file_path)
        except Exception as e:
            logger.warning("Could not load measurements from %s: %s", measurement_file_path, e)
            return {}
    else:
        # Return empty dict if no measurements available
        return {}


def set_length(expr, meas_dict):
    """Evaluate length expression with measurements.

    Calls eval() on the substituted expression. Input is assumed to come
    from a trusted .sm2d pattern file, not from user-supplied text.
    """
    try:
        result = float(expr)
    except (ValueError, TypeError):
        result = expr
        for key, val in meas_dict.items():
            result = re.sub(r'\b' + key + r'\b', str(val), result)

    try:
        return eval(result)  # nosec — input is a trusted pattern file
    except Exception:
        return expr


def evaluate_expression(expr):
    """Evaluate expressions including Line_ and CurrentLength references."""
    try:
        result = float(expr)
    except (ValueError, TypeError):
        if "Line" in expr:
            try:
                pattern = r"Line_([A-Za-z0-9_]+)_([A-Za-z0-9_]+)\s*([+\-*/][\d.\s]+)+$"
                match = re.match(pattern, expr)
                firstname = str(match.group(1))
                secondname = str(match.group(2))
                list_expression = re.findall(r"([+\-*/])\s*([\d.]+)", expr)
                expression = ''.join(op + val for op, val in list_expression)
                result = [firstname, secondname, expression]
                return result
            except AttributeError:
                pattern = r"Line_([A-Za-z0-9_]+)_([A-Za-z0-9_]+)$"
                match = re.match(pattern, expr)
                firstname = str(match.group(1))
                secondname = str(match.group(2))
                result = [firstname, secondname]
                return result

        elif "CurrentLength" in expr:
            result = ["CurrentLength", match.group(1)] if (match := re.match(r"CurrentLength(.+)$", expr)) else ["CurrentLength"]
            return result

    return expr


def find_point(pointsdict, name):
    """Find a point by name in the points dictionary."""
    for p in pointsdict.values():
        if isinstance(p, Point) and hasattr(p, 'name') and p.name == name:
            return p



def calc_point_of_contact(center_point, first_point, second_point, radius):
    """Calculate tangent point of contact."""
    dx = float(second_point.x - first_point.x)
    dy = float(second_point.y - first_point.y)

    if dx != 0:
        fx = first_point.x - center_point.x
        fy = first_point.y - center_point.y

        a = dx**2 + dy**2
        b = 2 * (fx * dx + fy * dy)
        c = fx**2 + fy**2 - radius**2
        discriminant = b**2 - 4 * a * c
        
        if discriminant < 0:
            raise ValueError("No tangent point exists with the given radius.")
        
        discriminant_sqrt = math.sqrt(discriminant)
        t1 = (-b + discriminant_sqrt) / (2 * a)

        x = first_point.x + t1 * dx
        y = first_point.y + t1 * dy
    else: 
        x = first_point.x
        dxm = center_point.x - first_point.x
        if abs(dxm) > radius:
            raise ValueError("No tangent point exists with the given radius.")
        dym = math.sqrt(radius**2 - dxm**2)
        if center_point.y > first_point.y:
            y = first_point.y + dym
        else:
            y = first_point.y - dym      

    return (float(round(x, 5)), float(round(y, 5)))


def calc_height_point(base_point, line_p1, line_p2):
    """Calculate foot of perpendicular from base_point to line."""
    dx = line_p2.x - line_p1.x
    dy = line_p2.y - line_p1.y
    
    px = base_point.x - line_p1.x
    py = base_point.y - line_p1.y
    
    line_length_sq = dx * dx + dy * dy
    
    if line_length_sq == 0:
        return (round(line_p1.x, 5), round(line_p1.y, 5))
    
    t = (px * dx + py * dy) / line_length_sq
    
    foot_x = line_p1.x + t * dx
    foot_y = line_p1.y + t * dy
    
    return (round(foot_x, 5), round(foot_y, 5))


def calc_distance_between_points(point, pointsdict, meas_dict):
    """Calculate distance for alongLine type points."""
    point.distance = set_length(point.length, meas_dict)
    point.distance = evaluate_expression(point.distance)
    
    if isinstance(point.distance, list): 
        if 'CurrentLength' in getattr(point, 'distance'):
            firstp_id = str(getattr(point, 'firstPoint'))
            secondp_id = str(getattr(point, 'secondPoint'))
            p1 = pointsdict.get(firstp_id)
            p2 = pointsdict.get(secondp_id)
            dist = math.sqrt((float(p1.x) - float(p2.x))**2 + (float(p1.y) - float(p2.y))**2)
            if len(getattr(point, 'distance')) > 1:
                expr = getattr(point, 'distance')[1]
                result = float(eval(f"dist {expr}"))
            else: 
                result = float(dist)
        else:
            distance = getattr(point, 'distance')
            firstp_name = distance[0]
            secondp_name = distance[1]
            p1 = find_point(pointsdict, firstp_name)
            p2 = find_point(pointsdict, secondp_name)
            dist = math.sqrt((float(p1.x) - float(p2.x))**2 + (float(p1.y) - float(p2.y))**2)
            if len(getattr(point, 'distance')) > 2:
                expr = distance[2]
                result = float(eval(f"dist {expr}"))
            else: 
                result = float(dist)

        point.distance = round(float(result), 5)
    return point


def calc_point_coord_endline(point, pointsdict, meas_dict):
    """Calculate coordinates for endLine type points."""
    angle    = int(float(set_length(getattr(point, 'angle'),    meas_dict)))
    distance = float(set_length(getattr(point, 'distance'), meas_dict))
    base_id = str(getattr(point, 'basePoint'))
    base_point = pointsdict.get(base_id)
    
    if base_point and hasattr(base_point, 'x') and hasattr(base_point, 'y'):
        if angle != 90 and angle != 270:
            point.x = round(float(base_point.x) + distance * np.cos(angle * np.pi/180), 5)
            point.y = round(float(base_point.y) + distance * np.sin(angle * np.pi/180), 5)
        elif angle == 90:
            point.x = round(float(base_point.x), 5)
            point.y = round(float(base_point.y) + distance, 5)
        elif angle == 270:
            point.x = round(float(base_point.x), 5)
            point.y = round(float(base_point.y) - distance, 5)
    return point


def calc_point_coord_alongline(point, pointsdict):
    """Calculate coordinates for alongLine type points."""
    firstp_id = str(getattr(point, 'firstPoint'))
    secondp_id = str(getattr(point, 'secondPoint'))
    firstp = pointsdict.get(firstp_id)
    secondp = pointsdict.get(secondp_id)
    distance = float(getattr(point, 'distance'))
    
    if firstp and hasattr(firstp, 'x') and hasattr(firstp, 'y') and secondp and hasattr(secondp, 'x') and hasattr(secondp, 'y'):
        deltx = float(secondp.x) - float(firstp.x)
        delty = float(secondp.y) - float(firstp.y)
        
        if deltx == 0 and delty != 0:
            point.x = round(float(firstp.x), 5)
            if float(secondp.y) > float(firstp.y):
                point.y = round(float(firstp.y) + float(distance), 5)
            elif float(secondp.y) < float(firstp.y):
                point.y = round(float(firstp.y) - float(distance), 5)
        elif deltx != 0 and delty != 0:
            alpha = np.arctan2(delty, deltx)
            length_along = distance
            point.x = round(float(firstp.x) + length_along * np.cos(alpha), 5)
            point.y = round(float(firstp.y) + length_along * np.sin(alpha), 5)
        elif delty == 0:
            point.y = round(float(firstp.y), 5)
            if float(secondp.x) > float(firstp.x):
                point.x = round(float(firstp.x) + float(distance), 5)
            elif float(secondp.x) < float(firstp.x):
                point.x = round(float(firstp.x) - float(distance), 5)
    return point


def calc_point_coord_intersectXY(point, pointsdict):
    """Calculate coordinates for intersectXY type points."""
    firstp_id = str(getattr(point, 'firstPoint'))
    secondp_id = str(getattr(point, 'secondPoint'))
    firstp = pointsdict.get(firstp_id)
    secondp = pointsdict.get(secondp_id)
    
    if firstp and hasattr(firstp, 'x') and hasattr(firstp, 'y') and secondp and hasattr(secondp, 'x') and hasattr(secondp, 'y'):
        point.x = round(float(firstp.x), 5)
        point.y = round(float(secondp.y), 5)
    return point


def calc_point_coord_lineIntersectAxis(point, pointsdict):
    """Calculate coordinates for lineIntersectAxis type points."""
    angle = int(getattr(point, 'angle'))
    base_point = pointsdict.get(str(getattr(point, 'basePoint')))
    p1 = pointsdict.get(str(getattr(point, 'p1Line')))
    p2 = pointsdict.get(str(getattr(point, 'p2Line')))

    if not (base_point and hasattr(base_point, 'x') and hasattr(base_point, 'y')):
        return point

    if float(p2.x) == float(p1.x):
        logger.warning("lineIntersectAxis: reference line is vertical (p1.x == p2.x); skipping point '%s'",
                       getattr(point, 'id', '?'))
        return point

    m2 = round((float(p2.y) - float(p1.y)) / (float(p2.x) - float(p1.x)), 7)
    n2 = round(float(p1.y) - m2 * float(p1.x), 7)

    if angle == 90 or angle == 270:
        point.x = round(float(base_point.x), 5)
        point.y = round(m2 * float(base_point.x) + n2, 5)
    elif angle == 0 or angle == 180:
        point.y = round(float(base_point.y), 5)
        if abs(m2) < 1e-10:
            logger.warning("lineIntersectAxis: reference line is horizontal, no unique intersection; skipping '%s'",
                           getattr(point, 'id', '?'))
            return point
        point.x = round((float(base_point.y) - n2) / m2, 5)
    else:
        m1 = round(float(np.tan(angle * np.pi / 180)), 7)
        n1 = round(float(base_point.y) - m1 * float(base_point.x), 7)
        denom = m1 - m2
        if abs(denom) < 1e-10:
            logger.warning("lineIntersectAxis: axis and reference line are parallel; skipping '%s'",
                           getattr(point, 'id', '?'))
            return point
        point.x = round((n2 - n1) / denom, 5)
        point.y = round(m1 * float(point.x) + n1, 5)

    return point


def calc_point_coord_pointOfContact(point, pointsdict):
    """Calculate coordinates for pointOfContact type points."""
    center_id = str(getattr(point, 'center'))
    first_id = str(getattr(point, 'firstPoint'))
    second_id = str(getattr(point, 'secondPoint'))
    
    center_point = pointsdict.get(center_id)
    first_point = pointsdict.get(first_id)
    second_point = pointsdict.get(second_id)
    
    radius_expr = getattr(point, 'radius')
    radius = float(radius_expr)

    contact_x, contact_y = calc_point_of_contact(center_point, first_point, second_point, radius)
    point.x = contact_x
    point.y = contact_y
    return point


def calc_point_coord_normal(point, pointsdict):
    """Calculate coordinates for normal type points."""
    firstp_id = str(getattr(point, 'firstPoint'))
    secondp_id = str(getattr(point, 'secondPoint'))
    firstp = pointsdict.get(firstp_id)
    secondp = pointsdict.get(secondp_id)
    distance = float(getattr(point, 'distance'))
    
    if firstp and hasattr(firstp, 'x') and hasattr(firstp, 'y') and secondp and hasattr(secondp, 'x') and hasattr(secondp, 'y'):
        deltx = float(secondp.x) - float(firstp.x)
        delty = float(secondp.y) - float(firstp.y)
        alpha = np.arctan2(delty, deltx)
        
        if deltx != 0:
            alpha = np.arctan2(delty, deltx) - np.deg2rad(90)
            point.x = round(float(firstp.x) + distance * np.sin(alpha), 5)
            point.y = round(float(firstp.y) + distance * np.cos(alpha), 5)
        else: 
            point.x = firstp.x - distance
            point.y = firstp.y
    return point


def calc_point_coord_height(point, pointsdict):
    """Calculate coordinates for height type points."""
    base_id = str(getattr(point, 'basePoint'))
    p1_id = str(getattr(point, 'p1Line'))
    p2_id = str(getattr(point, 'p2Line'))
    
    base_point = pointsdict.get(base_id)
    line_p1 = pointsdict.get(p1_id)
    line_p2 = pointsdict.get(p2_id)
    
    foot_x, foot_y = calc_height_point(base_point, line_p1, line_p2)
    point.x = foot_x
    point.y = foot_y
    return point


def flip_point_coords(source_point, p1line, p2line, alpha, c):
    """Calculate flipped coordinates across a line."""
    a = np.sqrt(((source_point.x - p1line.x)**2 + (source_point.y - p1line.y)**2))
    b = np.sqrt(((source_point.x - p2line.x)**2 + (source_point.y - p2line.y)**2))
    p = a**2 / c
    q = b**2 / c
    h = np.sqrt(p*q)
    
    new_x = round(float(source_point.x) + 2*h * np.cos(alpha), 5)
    new_y = round(float(source_point.y) + 2*h * np.sin(alpha), 5)
    
    return new_x, new_y


def calc_point_coord_flippingByLine(obj, pointsdict):
    """Calculate flipped coordinates for Point, Spline, or Line objects."""
    p1line_id = str(getattr(obj, 'p1Line'))
    p2line_id = str(getattr(obj, 'p2Line'))
    source_id = str(getattr(obj, 'sourceId'))
    
    p1line = pointsdict.get(p1line_id)
    p2line = pointsdict.get(p2line_id)
    source_obj = pointsdict.get(source_id)
    
    dx = float(p2line.x) - float(p1line.x)
    dy = float(p2line.y) - float(p1line.y)
    alpha = np.arctan2(dy, dx) - np.deg2rad(90)
    c = np.sqrt(dx**2 + dy**2)
    
    if isinstance(obj, Point):
        obj.x, obj.y = flip_point_coords(source_obj, p1line, p2line, alpha, c)
        name = getattr(source_obj, 'name', '')
        suffix = getattr(obj, 'suffix', '')
        obj.name = f"{name}{suffix}"
    
    elif isinstance(obj, Spline):
        suffix = getattr(obj, 'suffix', '')
        for srcpoint in source_obj.points:
            mir_x, mir_y = flip_point_coords(srcpoint, p1line, p2line, alpha, c)
            srcpoint_id = getattr(srcpoint, 'id', None)
            mir_id = f"{srcpoint_id}{suffix}"
            mir_point = Point(id=mir_id, x=mir_x, y=mir_y)
            obj.add_point(mir_point)
    
    elif isinstance(obj, Line):
        suffix = getattr(obj, 'suffix', '')
        for srcpoint in source_obj.points:
            mir_x, mir_y = flip_point_coords(srcpoint, p1line, p2line, alpha, c)
            srcpoint_id = getattr(srcpoint, 'id', None)
            mir_id = f"{srcpoint_id}{suffix}"
            mir_point = Point(id=mir_id, x=mir_x, y=mir_y)
            obj.add_point(mir_point)
   
    return obj


def calc_point_coord_flippingByAxis(obj, pointsdict):
    """Calculate flipped coordinates across a vertical (axisType=1) or horizontal (axisType=2) axis through center."""
    axis_type = str(getattr(obj, 'axisType', '1'))
    center_id = str(getattr(obj, 'center'))
    source_id = str(getattr(obj, 'sourceId'))

    center_point = pointsdict.get(center_id)
    source_obj = pointsdict.get(source_id)

    def mirror(px, py):
        if axis_type == '1':  # vertical axis x = center.x
            return round(2 * float(center_point.x) - float(px), 5), round(float(py), 5)
        else:               # horizontal axis y = center.y
            return round(float(px), 5), round(2 * float(center_point.y) - float(py), 5)

    if isinstance(obj, Point):
        obj.x, obj.y = mirror(source_obj.x, source_obj.y)
        suffix = getattr(obj, 'suffix', '')
        obj.name = f"{getattr(source_obj, 'name', '')}{suffix}"

    elif isinstance(obj, Spline):
        suffix = getattr(obj, 'suffix', '')
        for srcpoint in source_obj.points:
            mir_x, mir_y = mirror(srcpoint.x, srcpoint.y)
            mir_point = Point(id=f"{getattr(srcpoint, 'id', '')}{suffix}", x=mir_x, y=mir_y)
            obj.add_point(mir_point)

    elif isinstance(obj, Line):
        suffix = getattr(obj, 'suffix', '')
        for srcpoint in source_obj.points:
            mir_x, mir_y = mirror(srcpoint.x, srcpoint.y)
            mir_point = Point(id=f"{getattr(srcpoint, 'id', '')}{suffix}", x=mir_x, y=mir_y)
            obj.add_point(mir_point)

    return obj


def splines_with_coordinates(spline, pointsdict):
    """Add coordinates to spline control points."""
    for point in spline.points:
        pointid = str(getattr(point, 'id'))
        ref_point = pointsdict.get(pointid)
        if ref_point and hasattr(ref_point, 'x') and hasattr(ref_point, 'y'):
            point.x = ref_point.x
            point.y = ref_point.y
    return spline


def handle_vector(length, angle_deg):
    """Create a vector from length and angle."""
    if length is None or length == 0 or angle_deg is None:
        return np.zeros(2)
    angle_rad = np.deg2rad(angle_deg)
    return np.array([
        length * np.cos(angle_rad),
        length * np.sin(angle_rad)
    ])


def generate_spline_path_points(spline, num_points=10):
    """Generate interpolated points along a spline curve."""
    spline_id = getattr(spline, 'id', 'spline')
    points = spline.points
    
    if len(points) < 2:
        return spline
    
    point_counter = 0
    
    for i in range(len(points) - 1):
        p_start = points[i]
        p_end = points[i + 1]
        
        P0 = np.array([p_start.x, p_start.y], dtype=float)
        P3 = np.array([p_end.x, p_end.y], dtype=float)

        if len(points) == 2:
            h1 = handle_vector(
                getattr(p_start, "length1", 0),
                getattr(p_start, "angle1", 0)
            )
            P1 = P0 + h1
            
            h2 = handle_vector(
                getattr(p_end, "length2", 0),
                getattr(p_end, "angle2", 0)
            )
            P2 = P3 + h2
        
        elif len(points) > 2:
            h1 = handle_vector(
                getattr(p_start, "length2", 0),   # outgoing handle from p_start
                getattr(p_start, "angle2", 0)
            )
            P1 = P0 + h1

            h2 = handle_vector(
                getattr(p_end, "length1", 0),      # incoming handle to p_end
                getattr(p_end, "angle1", 0)
            )
            P2 = P3 + h2
        
        t_vals = np.linspace(0, 1, num_points)
        for t in t_vals:
            if i > 0 and t == 0:
                continue
            
            point = (
                (1 - t)**3 * P0 +
                3 * (1 - t)**2 * t * P1 +
                3 * (1 - t) * t**2 * P2 +
                t**3 * P3
            )
                        
            path_point = points[0].__class__(
                id=f"{spline_id}_{point_counter}",
                x=point[0],
                y=point[1]
            )
            spline.add_point(path_point)
            point_counter += 1
            
    return spline



def import_geometry_from_xml(rootfile, pointdict=None):
    """Import all geometry objects from XML calculation section."""
    calculation = rootfile.find('.//draftBlock/calculation')
    geometry_dict = {}
    
    if pointdict is None:
        pointdict = {}
    
    # Import points
    for point_elem in calculation.findall('point'):
        attr_dict = point_elem.attrib
        point_obj = Point(**attr_dict)
        point_id = point_elem.get('id')
        if point_id:
            geometry_dict[point_id] = point_obj
            pointdict[point_id] = point_obj
    
    # Import splines
    for spline_elem in calculation.findall('spline'):
        attr_dict = spline_elem.attrib
        spline_obj = Spline(**attr_dict)
        
        path_points = spline_elem.findall('pathPoint')
        
        if len(path_points) > 0:
            for path_point_elem in path_points:
                p_spline_id = int(path_point_elem.get('pSpline'))
                angle1 = float(path_point_elem.get('angle1', 0))
                angle2 = float(path_point_elem.get('angle2', 0))
                length1 = float(path_point_elem.get('length1', 0))
                length2 = float(path_point_elem.get('length2', 0))
                
                point_attrs = {
                    'id': p_spline_id,
                    'angle1': angle1,
                    'angle2': angle2,
                    'length1': length1,
                    'length2': length2
                }
                
                point_obj = Point(**point_attrs)
                spline_obj.add_point(point_obj)
        else:
            angle1 = float(spline_elem.get('angle1', 0))
            angle2 = float(spline_elem.get('angle2', 0))
            length1 = float(spline_elem.get('length1', 0))
            length2 = float(spline_elem.get('length2', 0))
            startpoint = int(spline_elem.get('point1'))
            endpoint = int(spline_elem.get('point4'))
            
            startpoint_attrs = {
                'id': startpoint,
                'angle1': angle1,
                'length1': length1
            }
            startpointobj = Point(**startpoint_attrs)
            spline_obj.add_point(startpointobj)
            
            endpoint_attrs = {
                'id': endpoint,
                'angle2': angle2,
                'length2': length2
            }
            endpointobj = Point(**endpoint_attrs)
            spline_obj.add_point(endpointobj)
        
        spline_id = spline_elem.get('id')
        if spline_id:
            geometry_dict[spline_id] = spline_obj
    
    # Import lines
    for line_elem in calculation.findall('line'):
        attr_dict = line_elem.attrib
        line_obj = Line(**attr_dict)
        
        line_id = line_elem.get('id')
        if line_id:
            geometry_dict[line_id] = line_obj
    
    # Import operations
    for operation_elem in calculation.findall('operation'):
        operation_type = operation_elem.get('type')
        p1_line = operation_elem.get('p1Line')
        p2_line = operation_elem.get('p2Line')
        axis_type = operation_elem.get('axisType')
        center = operation_elem.get('center')
        suffix = operation_elem.get('suffix', '')
        
        source_items = []
        source_block = operation_elem.find('source')
        if source_block is not None:
            for item in source_block.findall('item'):
                source_items.append({
                    'idObject': item.get('idObject'),
                    'alias': item.get('alias', ''),
                    'color': item.get('color', 'black'),
                    'lineType': item.get('lineType', 'solidLine')
                })
        
        destination_block = operation_elem.find('destination')
        if destination_block is not None:
            dest_items = destination_block.findall('item')
            for i, dest_item in enumerate(dest_items):
                dest_id = dest_item.get('idObject')
                
                source_obj = None
                if i < len(source_items):
                    source_id = source_items[i]['idObject']
                    source_obj = geometry_dict.get(source_id)
                
                if source_obj is not None:
                    if isinstance(source_obj, Point):
                        attr_dict = {
                            'id': dest_id,
                            'type': 'operation',
                            'operationType': operation_type,
                            'p1Line': p1_line,
                            'p2Line': p2_line,
                            'axisType': axis_type,
                            'center': center,
                            'suffix': suffix,
                            'sourceId': source_items[i]['idObject']
                        }

                        if dest_item.get('showPointName'):
                            attr_dict['showPointName'] = dest_item.get('showPointName')

                        new_obj = Point(**attr_dict)
                        if dest_id:
                            geometry_dict[dest_id] = new_obj
                            pointdict[dest_id] = new_obj

                    elif isinstance(source_obj, Spline):
                        attr_dict = {
                            'id': dest_id,
                            'type': 'operation',
                            'operationType': operation_type,
                            'p1Line': p1_line,
                            'p2Line': p2_line,
                            'axisType': axis_type,
                            'center': center,
                            'suffix': suffix,
                            'sourceId': source_items[i]['idObject']
                        }

                        new_obj = Spline(**attr_dict)
                        if dest_id:
                            geometry_dict[dest_id] = new_obj

                    elif isinstance(source_obj, Line):
                        attr_dict = {
                            'id': dest_id,
                            'type': 'operation',
                            'operationType': operation_type,
                            'p1Line': p1_line,
                            'p2Line': p2_line,
                            'axisType': axis_type,
                            'center': center,
                            'suffix': suffix,
                            'sourceId': source_items[i]['idObject']
                        }

                        new_obj = Line(**attr_dict)
                        if dest_id:
                            geometry_dict[dest_id] = new_obj
                else:
                    attr_dict = {
                        'id': dest_id,
                        'type': 'operation',
                        'operationType': operation_type,
                        'p1Line': p1_line,
                        'p2Line': p2_line,
                        'axisType': axis_type,
                        'center': center,
                        'suffix': suffix
                    }

                    if i < len(source_items):
                        attr_dict['sourceId'] = source_items[i]['idObject']

                    if dest_item.get('showPointName'):
                        attr_dict['showPointName'] = dest_item.get('showPointName')

                    new_obj = Point(**attr_dict)
                    if dest_id:
                        geometry_dict[dest_id] = new_obj
                        pointdict[dest_id] = new_obj

    geometry_dict = dict(sorted(geometry_dict.items(), key=lambda x: int(x[0])))
    
    return geometry_dict


def calculate_all_coordinates(geometry_dict, meas_dict):
    """Calculate coordinates for all geometry objects."""
    for key, object in geometry_dict.items():
        if isinstance(object, Point):
            point = object
            if hasattr(point, 'length'):
                point = calc_distance_between_points(point, geometry_dict, meas_dict)
            if getattr(point, 'type', None) == 'endLine':
                point = calc_point_coord_endline(point, geometry_dict, meas_dict)
            elif getattr(point, 'type', None) == 'alongLine':
                point = calc_point_coord_alongline(point, geometry_dict)
            elif getattr(point, 'type', None) == 'intersectXY':
                point = calc_point_coord_intersectXY(point, geometry_dict)
            elif getattr(point, 'type', None) == 'lineIntersectAxis':
                point = calc_point_coord_lineIntersectAxis(point, geometry_dict)
            elif getattr(point, 'type', None) == 'pointOfContact':
                point = calc_point_coord_pointOfContact(point, geometry_dict)
            elif getattr(point, 'type', None) == 'normal':
                point = calc_point_coord_normal(point, geometry_dict)
            elif getattr(point, 'type', None) == 'height':
                point = calc_point_coord_height(point, geometry_dict)
            elif getattr(point, 'operationType', None) == 'flippingByLine':
                point = calc_point_coord_flippingByLine(point, geometry_dict)
            elif getattr(point, 'operationType', None) == 'flippingByAxis':
                point = calc_point_coord_flippingByAxis(point, geometry_dict)

            geometry_dict[key] = point

        if isinstance(object, Spline):
            spline = object
            if len(spline.points) > 0:
                spline = splines_with_coordinates(spline, geometry_dict)
                spline = generate_spline_path_points(spline, num_points=10)
            elif getattr(spline, 'operationType', None) == 'flippingByLine':
                spline = calc_point_coord_flippingByLine(spline, geometry_dict)
            elif getattr(spline, 'operationType', None) == 'flippingByAxis':
                spline = calc_point_coord_flippingByAxis(spline, geometry_dict)
            geometry_dict[key] = spline

        if isinstance(object, Line):
            line = object
            if not hasattr(line, 'operationType'):
                firstPointid = str(getattr(line, 'firstPoint', None))
                p1 = geometry_dict.get(firstPointid)
                if p1:
                    line.add_point(p1)

                secondPointid = str(getattr(line, 'secondPoint', None))
                p2 = geometry_dict.get(secondPointid)
                if p2:
                    line.add_point(p2)

            elif getattr(line, 'operationType', None) == 'flippingByLine':
                line = calc_point_coord_flippingByLine(line, geometry_dict)
            elif getattr(line, 'operationType', None) == 'flippingByAxis':
                line = calc_point_coord_flippingByAxis(line, geometry_dict)
            
            geometry_dict[key] = line

    return geometry_dict


def add_modeling_info(rootfile, objectdict):
    """Extract modeling section and link to geometry objects."""
    modeling = rootfile.find('.//draftBlock/modeling')
    modelingdict = {}
    
    for element in modeling:
        modeling_id = element.get('id')
        id_object = element.get('idObject')
        in_use = element.get('inUse', 'false')
        model_type = element.get('type')

        if id_object in objectdict:
            obj = copy.deepcopy(objectdict[id_object])
            setattr(obj, 'inUse', in_use == 'true')
            setattr(obj, 'idObject', id_object)
            setattr(obj, 'modelingType', model_type)
            setattr(obj, 'modelingId', modeling_id)
            modelingdict[modeling_id] = obj
    
    return modelingdict


def parse_pieces_with_node_order(root, modellingdict):
    """Parse pieces from XML with node order preserved."""
    pieces_dict = {}
    
    pieces = root.findall('.//piece')
    
    for piece_element in pieces:
        piece_id = piece_element.get('id')
        piece_name = piece_element.get('name')
        united = piece_element.get('united', 'false') == 'true'
        seam_allowance = piece_element.get('seamAllowance', 'false') == 'true'
        
        data_element = piece_element.find('data')
        on_fold = data_element.get('onFold', 'false') == 'true' if data_element is not None else False
        fold_position = data_element.get('foldPosition') if data_element is not None else None
        pattern_rotation = data_element.get('rotation') if data_element is not None else None
        
        grainline_element = piece_element.find('grainline')
        grainline_rotation = grainline_element.get('rotation') if grainline_element is not None else None
        
        piece = Piece(
            id=piece_id,
            name=piece_name,
            united=united,
            seamAllowance=seam_allowance,
            onFold=on_fold,
            foldPosition=fold_position,
            patternRotation=pattern_rotation,
            grainlineRotation=grainline_rotation
        )
        
        # Store ordered nodes list
        piece.ordered_nodes = []
        
        nodes = piece_element.find('nodes')
        if nodes is not None:
            for node in nodes:
                id_object = node.get('idObject')
                node_type = node.get('type')
                reverse = node.get('reverse', '0') == '1'
                
                if id_object in modellingdict:
                    modeling_obj = modellingdict[id_object]
                    
                    # Store node info with order
                    node_info = {
                        'idObject': id_object,
                        'type': node_type,
                        'object': modeling_obj,
                        'reverse': reverse
                    }
                    piece.ordered_nodes.append(node_info)
                    
                    # Also add to the original lists
                    if node_type == 'NodePoint' and isinstance(modeling_obj, Point):
                        piece.add_point(modeling_obj)
                    elif node_type in ['NodeSpline', 'NodeSplinePath'] and isinstance(modeling_obj, Spline):
                        piece.add_spline(modeling_obj)
                    elif node_type == 'NodeLine' and isinstance(modeling_obj, Line):
                        piece.add_line(modeling_obj)
       
        pieces_dict[piece_id] = piece
    
    return pieces_dict



def parse_pattern_file(pattern_file_path: str, measurement_file_path: Optional[str] = None) -> dict:

    # Load XML
    tree = ET.parse(pattern_file_path)
    root = tree.getroot()
    
    # Load measurements if provided
    meas_dict = load_measurements(measurement_file_path)
    
    # Import geometry from XML
    geometry_dict = import_geometry_from_xml(root)
    
    # Calculate all coordinates
    geometry_coord = calculate_all_coordinates(geometry_dict, meas_dict)
    
    # Add modeling information
    modelling_objects = add_modeling_info(root, geometry_coord)
    
    # Parse pieces with node order
    pieces_dict = parse_pieces_with_node_order(root, modelling_objects)
    
    return pieces_dict



def get_piece_outline_coords(piece) -> tuple:
    """
    Extract ordered outline coordinates from a piece.
    
    Parameters:
    -----------
    piece : Piece object
        A piece with .ordered_nodes attribute
        
    Returns:
    --------
    tuple : (x_coords, y_coords) as lists of floats
    
    Example:
    --------
    >>> x, y = get_piece_outline_coords(piece)
    >>> plt.plot(x + [x[0]], y + [y[0]], '-o')  # Close the shape
    """
    outline_x = []
    outline_y = []
    
    if not hasattr(piece, 'ordered_nodes'):
        raise ValueError("Piece must have ordered_nodes attribute. Use parse_pattern_file() to create pieces.")
    
    for node_info in piece.ordered_nodes:
        obj = node_info['object']
        node_type = node_info['type']
        reverse = node_info.get('reverse', False)
        
        if node_type == 'NodePoint':
            if hasattr(obj, 'x') and hasattr(obj, 'y'):
                outline_x.append(float(obj.x))
                outline_y.append(float(obj.y))
        
        elif node_type in ['NodeSpline', 'NodeSplinePath']:
            if hasattr(obj, 'points'):
                points = [p for p in obj.points if "_" in str(p.id)]
                if reverse:
                    points = list(reversed(points))
                for p in points:
                    if hasattr(p, 'x') and hasattr(p, 'y'):
                        outline_x.append(float(p.x))
                        outline_y.append(float(p.y))
        
        elif node_type == 'NodeLine':
            if hasattr(obj, 'points'):
                points = obj.points
                if reverse:
                    points = list(reversed(points))
                for p in points:
                    if hasattr(p, 'x') and hasattr(p, 'y'):
                        outline_x.append(float(p.x))
                        outline_y.append(float(p.y))
    
    return (outline_x, outline_y)


if __name__ == "__main__":
    # Example usage when run as a script
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python seamly_parser.py <pattern_file.sm2d> [measurement_file.smis]")
        sys.exit(1)
    
    pattern_file = sys.argv[1]
    measurement_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"Parsing pattern: {pattern_file}")
    if measurement_file:
        print(f"Using measurements: {measurement_file}")
    
    pieces = parse_pattern_file(pattern_file, measurement_file)
    
    print(f"\nFound {len(pieces)} pieces:")
    for piece_id, piece in pieces.items():
        print(f"  - {piece.name} (ID: {piece.id}): {len(piece.ordered_nodes)} nodes")

