"""Contains the decoding logic for line location"""

from typing import List, Optional
from openlr import LineLocationReference, LocationReferencePoint
from ..maps import MapReader
from ..maps.abstract import GeoTool
from ..observer import DecoderObserver
from .candidate_functions import nominate_candidates, match_tail
from .line_location import build_line_location, LineLocation
from .routes import Route
from .configuration import Config
from logging import debug
from .error import LRDecodeError



def dereference_path(
        lrps: List[LocationReferencePoint],
        reader: MapReader,
        config: Config,
        observer: Optional[DecoderObserver],
        geo_tool: GeoTool
) -> List[Route]:
    """Decode the location reference path, without considering any offsets"""
    first_lrp = lrps[0]
    first_candidates = list(nominate_candidates(first_lrp, reader, config, observer, False, geo_tool))
    if not first_candidates:
        msg = f"No candidates found for first LRP {first_lrp}"
        debug(msg)
        raise LRDecodeError(msg)

    linelocationpath = match_tail(first_lrp, first_candidates, lrps[1:], reader, config, observer, geo_tool)
    return linelocationpath


def decode_line(reference: LineLocationReference, reader: MapReader, config: Config,
                observer: Optional[DecoderObserver], geo_tool: GeoTool) -> LineLocation:
    """Decodes an openLR line location reference

    Candidates are searched in a radius of `radius` meters around an LRP."""
    parts = dereference_path(reference.points, reader, config, observer, geo_tool)
    return build_line_location(parts, reference, geo_tool)
