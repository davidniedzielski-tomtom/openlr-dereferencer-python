"""Contains the abstract observer class for the decoder"""
from abc import abstractmethod
from typing import Sequence, List, Tuple

from openlr import LocationReferencePoint

from ..decoding.candidate import Candidate
from ..decoding.routes import PointOnLine
from ..maps import Line


class DecoderObserver:
    """Abstract class representing an observer to the OpenLR decoding process"""

    @abstractmethod
    def on_candidate_found(self, lrp: LocationReferencePoint, candidate: Candidate):
        """Called by the decoder when it finds a candidate for a location reference point"""

    @abstractmethod
    def on_candidate_rejected(self, lrp: LocationReferencePoint, candidate: Candidate, reason: str):
        """Called by the decoder when a candidate for a location reference point is rejected"""

    @abstractmethod
    def on_candidate_rejected_bearing(self, lrp: LocationReferencePoint, candidate: Candidate, bearing: float,
                                      bearing_diff: float, max_bearing_deviation: float):
        """
        Called by the decoder when a candidate for a location reference point is rejected due to excessive bearing difference
        """

    @abstractmethod
    def on_candidate_score(lrp: LocationReferencePoint, candidate: PointOnLine, geo_score: float, fow_score: float,
                           frc_score: float, bear_score: float, total_score: float):
        """
        Called by the decoder when a candidate for a location reference point is scored
        """

    @abstractmethod
    def on_candidate_rejected_frc(lrp: LocationReferencePoint, candidate: Candidate, tolerated_frc: int):
        """
        Called by the decoder when a candidate for a location reference point is rejected due to incompatible FRC
        """

    @abstractmethod
    def on_no_candidates_found(self, lrp: LocationReferencePoint):
        """Called by the decoder when it finds no candidates for a location reference point"""

    @abstractmethod
    def on_candidates_found(self, lrp: LocationReferencePoint, candidates: List[Candidate]):
        """Called by the decoder when it finds no candidates for a location reference point"""

    @abstractmethod
    def on_route_fail_length(self, lrps: Tuple[LocationReferencePoint, LocationReferencePoint],
                             candidates: Tuple[Candidate, Candidate], route: List[Candidate], actual_length,
                             min_length: float, max_len_float):
        """Called by the decoder when it finds no candidates for a location reference point"""

    @abstractmethod
    def on_route_success(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                         from_line: Line, to_line: Line, path: Sequence[Line]):
        """Called after the decoder successfully finds a route between two candidate
        lines for successive location reference points"""

    @abstractmethod
    def on_route_fail(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                      from_line: Line, to_line: Line, reason: str):
        """Called after the decoder fails to find a route between two candidate
        lines for successive location reference points"""

    @abstractmethod
    def on_matching_fail(self, from_lrp: LocationReferencePoint, to_lrp: LocationReferencePoint,
                         from_candidates: Sequence[Candidate], to_candidates: Sequence[Candidate], reason: str):
        """Called after none of the candidate pairs for two LRPs were matching.
        
        The only way of recovering is to go back and discard the last bit of
        the dereferenced line location, if possible."""
