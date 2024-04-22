"""Defines data types out of which line locations consist"""

from typing import NamedTuple, Tuple, Optional, List
from shapely.geometry import LineString
from shapely.ops import substring
from openlr import Coordinates
from ..maps.abstract import Line, path_length, GeoTool
from functools import lru_cache


class PointOnLine(NamedTuple):
    """A point on the road network"""
    #: The line element on which the point resides
    line: Line
    # Specifies the relative offset of the point.
    # Its value is member of the interval [0.0, 1.0].
    # A value of 0 references the starting point of the line.
    relative_offset: float

    def _geometry_length_from_start(self, geo_tool: GeoTool):
        geometry_length = geo_tool.line_string_length(self.line.geometry)
        return geometry_length * self.relative_offset

    @lru_cache(maxsize=1)
    def position(self, geo_tool: GeoTool) -> Coordinates:
        """Returns the actual geo position"""
        return geo_tool.interpolate(self.line.coordinates(), self._geometry_length_from_start(geo_tool))

    @lru_cache(maxsize=1)
    def distance_from_start(self) -> float:
        """Returns the distance in meters from the start of the line to the point"""
        return self.relative_offset * self.line.length

    @lru_cache(maxsize=1)
    def distance_to_end(self) -> float:
        """Returns the distance in meters from the point to the end of the line"""
        return (1.0 - self.relative_offset) * self.line.length

    def split(self, geo_tool: GeoTool) -> Tuple[Optional[LineString], Optional[LineString]]:
        """Splits the Line element that this point is along and returns the parts"""
        return geo_tool.split_line(self.line.geometry, self._geometry_length_from_start(geo_tool))

    @classmethod
    def from_abs_offset(cls, line: Line, meters_into: float):
        """Build a PointOnLine from an absolute offset value.

        Negative offsets are recognized and subtracted."""
        if meters_into >= 0.0:
            return cls(line, meters_into / line.length)
        else:
            negative_meters_into = line.length + meters_into
            return cls(line, negative_meters_into / line.length)


class Route(NamedTuple):
    """A part of a line location path. May contain partial lines."""
    #: The point with which this location is starting
    start: PointOnLine
    #: While the first and the last line may be partial, these are the intermediate lines.
    path_inbetween: List[Line]
    #: The point on which this location is ending
    end: PointOnLine
    #: GeoTool reference that understands this route's SRID
    geo_tool: GeoTool

    @property
    def lines(self) -> List[Line]:
        """Returns all lines that take part in the route"""
        result = [self.start.line]
        for line in self.path_inbetween:
            if line.line_id != result[-1].line_id:
                result.append(line)
        if self.end.line.line_id == result[-1].line_id:
            result.pop()
        result.append(self.end.line)
        return result

    def length(self) -> float:
        """Length of this line location part in meters"""
        lines = self.lines
        result = path_length(lines)
        if self.start.relative_offset > 0.0:
            result -= self.start.distance_from_start()
        if self.end.relative_offset < 1.0:
            result -= self.end.distance_to_end()
        return result

    @property
    def absolute_start_offset(self) -> float:
        """Offset on the starting line in meters"""
        return self.start.distance_from_start()

    @property
    def absolute_end_offset(self) -> float:
        """Offset on the ending line in meters"""
        return self.end.distance_to_end()

    @property
    def shape(self) -> LineString:
        """Returns the shape of the route. The route has to be continuous."""
        if self.start.line.line_id == self.end.line.line_id:
            return substring(
                self.start.line.geometry,
                self.start.relative_offset,
                self.end.relative_offset,
                normalized=True
            )

        result = []
        first = self.start.split(self.geo_tool)[1]
        last = self.end.split(self.geo_tool)[0]
        if first is not None:
            result.append(first)
        result += [line.geometry for line in self.path_inbetween]
        if last is not None:
            result.append(last)

        return self.geo_tool.join_lines(result)

    def coordinates(self) -> List[Coordinates]:
        """Returns all Coordinates of this line location"""
        return [Coordinates(lon, lat) for (lon, lat) in self.shape.coords]
