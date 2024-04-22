"""Functions for reckoning with paths, bearing, and offsets"""

from logging import debug
from math import degrees
from typing import List

from openlr import Coordinates, LocationReferencePoint
from shapely.geometry import LineString, Point

from .error import LRDecodeError
from .routes import Route, PointOnLine
from ..maps import Line
from ..maps.abstract import GeoTool


def remove_offsets(path: Route, p_off: float, n_off: float, geo_tool: GeoTool) -> Route:
    """Remove start+end offsets, measured in meters, from a route and return the result"""
    debug("Will consider positive offset = %.02fm and negative offset %.02fm.", p_off, n_off)
    lines = path.lines
    debug("This route consists of %s and is %.02fm long.", lines, path.length())
    # Remove positive offset
    debug("first line's offset is %.02f", path.absolute_start_offset)
    remaining_poff = p_off + path.absolute_start_offset
    while remaining_poff >= lines[0].length:
        debug("Remaining positive offset %.02f is greater than the first line. Removing it.", remaining_poff)
        remaining_poff -= lines.pop(0).length
        if not lines:
            raise LRDecodeError("Offset is bigger than line location path")
    # Remove negative offset
    remaining_noff = n_off + path.absolute_end_offset
    while remaining_noff >= lines[-1].length:
        debug("Remaining negative offset %.02f is greater than the last line. Removing it.", remaining_noff)
        remaining_noff -= lines.pop().length
        if not lines:
            raise LRDecodeError("Offset is bigger than line location path")
    start_line = lines.pop(0)
    if lines:
        end_line = lines.pop()
    else:
        end_line = start_line
    return Route(PointOnLine.from_abs_offset(start_line, remaining_poff), lines,
                 PointOnLine.from_abs_offset(end_line, end_line.length - remaining_noff), geo_tool)


def coords(lrp: LocationReferencePoint) -> Coordinates:
    """Return the coordinates of an LRP"""
    return Coordinates(lrp.lon, lrp.lat)


def project(line: Line, coord: Coordinates) -> PointOnLine:
    """Computes the nearest point to `coord` on the line

    Returns: The point on `line` where this nearest point resides"""
    fraction = line.geometry.project(Point(coord.lon, coord.lat), normalized=True)

    # to_projection_point = substring(line.geometry, 0.0, fraction, normalized=True)

    # meters_to_projection_point = geo_tool.line_string_length(to_projection_point)
    # #geometry_length = geo_tool.line_string_length(line.geometry)
    # geometry_length = line.length

    # length_fraction = meters_to_projection_point / geometry_length

    # return PointOnLine(line, length_fraction)
    return PointOnLine(line, fraction)


def linestring_coords(line: LineString) -> List[Coordinates]:
    """Returns the edges of the line geometry as Coordinate list"""
    return [Coordinates(*point) for point in line.coords]


def compute_bearing(candidate: PointOnLine, is_last_lrp: bool, bear_dist: float,
                    geo_tool: GeoTool) -> float:
    """Returns the bearing angle of a partial line in degrees in the range 0.0 . 360.0"""

    # check if the bearing and origin points coincide, and return early if so
    if (not is_last_lrp and candidate.position == 1.0) or (is_last_lrp and candidate.position == 0.0):
        return 0.0

    # start_fragment:float = candidate.relative_offset
    # end_fragment:float = 0.0

    # bearing_fragment:float = bear_dist / candidate.line.length
    # if not is_last_lrp:
    #     end_fragment = candidate.relative_offset + bearing_fragment
    # else:
    #     end_fragment = candidate.relative_offset - bearing_fragment

    # ls = substring(candidate.line.geometry, start_fragment, end_fragment, normalized=True) 
    # coords = ls.coords
    # bear = geo_tool.bearing(Coordinates(*coords[0]), Coordinates(*coords[-1]))
    # return degrees(bear) % 360

    coordinates = candidate.line.coordinates()
    origin = geo_tool.interpolate(coordinates, candidate.distance_from_start())

    # see if we can optimize in the common case of two-point road segments
    if len(coordinates) == 2:
        bearing_point = coordinates[0] if is_last_lrp else coordinates[-1]
    else:
        if is_last_lrp:
            bearing_point = geo_tool.interpolate(coordinates, candidate.distance_from_start() - bear_dist)
        else:
            bearing_point = geo_tool.interpolate(coordinates, candidate.distance_from_start() + bear_dist)
    bear = geo_tool.bearing(origin, bearing_point)
    return degrees(bear) % 360
