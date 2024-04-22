"""Helper functions for A*"""

from functools import lru_cache
from ..abstract import Node, GeoTool


class LRPathNotFoundError(Exception):
    """No path was found through the map"""


@lru_cache(maxsize=2)
def heuristic(current: Node, target: Node, geo_tool: GeoTool) -> float:
    """Estimated cost from current to target.

    We use geographical distance here as heuristic here."""
    return geo_tool.distance(current.coordinates, target.coordinates)


def tautology(_) -> bool:
    """Returns always True, used as default line filter function."""
    return True
