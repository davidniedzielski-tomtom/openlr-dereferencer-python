"""Some geo coordinates related tools"""
from math import radians, degrees
from typing import Sequence, Tuple, Optional
from geographiclib.geodesic import Geodesic
from openlr import Coordinates
from shapely.geometry import LineString
from itertools import tee
from .abstract import GeoTool


def pairwise(iterable):
    """s -> (s0,s1), (s1,s2), (s2, s3), ..."""
    first, second = tee(iterable)
    next(second, None)
    return zip(first, second)


class WGS84GeoTool(GeoTool):
    """
    Subclass of GeoTool specialized for WGS84 target maps
    """

    geod = Geodesic.WGS84

    def transform_coordinate(self, coord: Coordinates) -> Coordinates:
        """ Transforms a WGS84 coordinate into the local CRS """
        return coord

    def distance(self, point_a: Coordinates, point_b: Coordinates) -> float:
        """Returns the distance of two WGS84 coordinates on our planet, in meters"""
        (lon1, lat1) = point_a.lon, point_a.lat
        (lon2, lat2) = point_b.lon, point_b.lat
        line = self.geod.Inverse(lat1, lon1, lat2, lon2, Geodesic.DISTANCE)
        # According to https://geographiclib.sourceforge.io/1.50/python/, the distance between
        # point 1 and 2 is stored in the attribute `s12`.
        return line["s12"]

    def line_string_length(self, line_string: LineString) -> float:
        """Returns the length of a line string in meters"""
        length = 0

        for (coord_a, coord_b) in pairwise(line_string.coords):
            lvals = self.geod.Inverse(coord_a[1], coord_a[0], coord_b[1], coord_b[0], Geodesic.DISTANCE)
            length += lvals["s12"]

        return length

    def bearing(self, point_a: Coordinates, point_b: Coordinates) -> float:
        """Returns the angle between self and other relative to true north

        The result of this function is between -pi, pi, including them"""
        line = self.geod.Inverse(point_a.lat, point_a.lon, point_b.lat, point_b.lon, Geodesic.AZIMUTH)
        # According to https://geographiclib.sourceforge.io/1.50/python/, the azimuth at the
        # first point in degrees is stored as the attribute `azi1`.
        return radians(line["azi1"])

    def extrapolate(self, point: Coordinates, dist: float, angle: float) -> Coordinates:
        """Creates a new point that is `dist` meters away in direction `angle`"""
        lon, lat = point.lon, point.lat
        line = self.geod.Direct(lat, lon, degrees(angle), dist)
        # According to https://geographiclib.sourceforge.io/1.50/python/, the attributes `lon2`
        # and `lat2` store the second point.
        return Coordinates(line["lon2"], line["lat2"])

    def interpolate(self, path: Sequence[Coordinates], distance_meters: float) -> Coordinates:
        """Go `distance` meters along the `path` and return the resulting point

        When the length of the path is too short, returns its last coordinate"""
        remaining_distance = distance_meters
        segments = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
        for (point1, point2) in segments:
            segment_length = self.distance(point1, point2)
            if remaining_distance == 0.0:
                return point1
            if remaining_distance < segment_length:
                angle = self.bearing(point1, point2)
                return self.extrapolate(point1, remaining_distance, angle)
            remaining_distance -= segment_length
        return segments[-1][1]

    def split_line(self, line: LineString, meters_into: float) -> Tuple[Optional[LineString], Optional[LineString]]:
        """Splits a line at `meters_into` meters and returns the two parts. A part is None if it would be a Point"""
        first_part = []
        second_part = []
        remaining_offset = meters_into
        splitpoint = None
        for (point_from, point_to) in pairwise(line.coords):
            if splitpoint is None:
                first_part.append(point_from)
                (coord_from, coord_to) = (Coordinates(*point_from), Coordinates(*point_to))
                segment_length = self.distance(coord_from, coord_to)
                if remaining_offset < segment_length:
                    splitpoint = self.interpolate([coord_from, coord_to], remaining_offset)
                    if splitpoint != coord_from:
                        first_part.append(splitpoint)
                    second_part = [splitpoint, point_to]
                remaining_offset -= segment_length
            else:
                second_part.append(point_to)
        if splitpoint is None:
            return line, None
        first_part = LineString(first_part) if len(first_part) > 1 else None
        second_part = LineString(second_part) if len(second_part) > 1 else None
        return first_part, second_part

    def join_lines(self, lines: Sequence[LineString]) -> LineString:
        coords = []
        last = None

        for line in lines:
            cs = line.coords
            first = cs[0]

            if last is None:
                coords.append(first)
            else:
                if first != last:
                    raise ValueError("Lines are not connected")

            coords.extend(cs[1:])
            last = cs[-1]

        return LineString(coords)
