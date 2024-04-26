"""Contains functions for candidate searching and map matching"""

from itertools import product
from logging import debug,error
from typing import Optional, Iterable, List, Tuple, Set, Dict, Hashable

from openlr import FRC, LocationReferencePoint

from .candidate import Candidate
from .configuration import Config
from .error import LRDecodeError
from .path_math import coords, project, compute_bearing
from .routes import Route
from .scoring import score_lrp_candidate, angle_difference
from ..maps import shortest_path, MapReader, Line, Node
from ..maps.a_star import LRPathNotFoundError
from ..maps.abstract import GeoTool
from ..observer import DecoderObserver


def make_candidates(lrp: LocationReferencePoint, line: Line, config: Config, observer: Optional[DecoderObserver],
                    is_last_lrp: bool, geo_tool: GeoTool) -> Iterable[Candidate]:
    """Returns one or none LRP candidates based on the given line"""
    # When the line is of length zero, we expect that also the adjacent lines are considered as candidates, hence
    # we don't need to project on the point that is the degenerated line.
    if line.geometry.length == 0:
        return
    point_on_line = project(line, coords(lrp))
    reloff = point_on_line.relative_offset
    # In case the LRP is not the last LRP
    if not is_last_lrp:
        # Snap to the relevant end of the line, only if the node is not a simple connection node between two lines:
        # so it does not look like this: ----*-----
        if abs(point_on_line.distance_from_start()) <= config.candidate_threshold and is_valid_node(line.start_node):
            reloff = 0.0
        # If the projection onto the line is close to the END of the line,
        # discard the point since we expect that the start of
        # an adjacent line will be considered as candidate and that would be the better candidate.
        else:
            if abs(point_on_line.distance_to_end()) <= config.candidate_threshold and is_valid_node(line.end_node):
                return
    # In case the LRP is the last LRP
    if is_last_lrp:
        # Snap to the relevant end of the line, only if the node is not a simple connection node between two lines:
        # so it does not look like this: ----*-----
        if abs(point_on_line.distance_to_end()) <= config.candidate_threshold and is_valid_node(line.end_node):
            reloff = 1.0
        else:
            # If the projection onto the line is close to the START of the line,
            # discard the point since we expect that the end of an adjacent line
            # will be considered as candidate and that would be the better candidate.
            if point_on_line.distance_from_start() <= config.candidate_threshold and is_valid_node(line.start_node):
                return
    # Drop candidate if there is no partial line left
    if is_last_lrp and reloff <= 0.0 or not is_last_lrp and reloff >= 1.0:
        return
    candidate = Candidate(line, reloff)
    bearing = compute_bearing(candidate, is_last_lrp, config.bear_dist, geo_tool)
    bear_diff = angle_difference(bearing, lrp.bear)
    if line.frc > config.tolerated_lfrc[lrp.lfrcnp]:
        msg = f"not considering {candidate} because its frc ({line.frc}) is less than the minimum allowed frc ({config.tolerated_lfrc[lrp.lfrcnp]})"
        debug(msg)
        if observer is not None:
            observer.on_candidate_rejected_frc(lrp, candidate, config.tolerated_lfrc[lrp.lfrcnp])
        return

    if abs(bear_diff) > config.max_bear_deviation:
        debug("Not considering %s because the bearing difference is %.02f°. (bear: %.02f. lrp bear: %.02f)", candidate,
              bear_diff, bearing, lrp.bear)
        if observer is not None:
            observer.on_candidate_rejected_bearing(lrp, candidate, bearing, bear_diff, config.max_bear_deviation)

        debug(f"Not considering %s because the bearing difference is %s ° (bear: %s. lrp bear: %s)", candidate,
              bear_diff, bearing, lrp.bear)
        return
    candidate.score = score_lrp_candidate(lrp, candidate, config, is_last_lrp, observer, geo_tool)
    if candidate.score < config.min_score:
        if observer is not None:
            observer.on_candidate_rejected(lrp, candidate,
                                           f"Candidate score = {candidate.score} lower than min. score = {config.min_score}", )
        debug(f"Not considering {candidate}: candidate score = {candidate.score} < min. score = {config.min_score}")
        return
    if observer is not None:
        observer.on_candidate_found(lrp, candidate, )
    yield candidate


def nominate_candidates(lrp: LocationReferencePoint, reader: MapReader, config: Config,
                        observer: Optional[DecoderObserver], is_last_lrp: bool, geo_tool: GeoTool) -> Iterable[
    Candidate]:
    "Yields candidate lines for the LRP along with their score."
    debug("Finding candidates for LRP %s at %s in radius %.02f", lrp, coords(lrp), config.search_radius)
    for line in reader.find_lines_close_to(coords(lrp), config.search_radius):
        yield from make_candidates(lrp, line, config, observer, is_last_lrp, geo_tool)


def get_candidate_route(start: Candidate, dest: Candidate, lfrc: FRC, maxlen: float, geo_tool) -> Optional[Route]:
    """Returns the shortest path between two LRP candidates, excluding partial lines.

    If it is longer than `maxlen`, it is treated as if no path exists.

    Args:
        start:
            The starting point.
        dest:
            The ending point.
        lfrc:
            "lowest frc". Line objects from map_reader with an FRC lower than lfrc will be ignored.
        maxlen:
            Pathfinding will be canceled after exceeding a length of maxlen.
        geo_tool:
            A reference to an instance of GeoTool that understands the route's CRS

    Returns:
        If a matching shortest path is found, it is returned as a list of Line objects.
        The returned path excludes the lines the candidate points are on.
        If there is no matching path found, None is returned.
    """
    debug("Try to find path between %s,%s", start, dest)
    if start.line.line_id == dest.line.line_id:
        return Route(start, [], dest, geo_tool)
    debug("Finding path between nodes %s,%s", start.line.end_node.node_id, dest.line.start_node.node_id)
    linefilter = lambda line: line.frc <= lfrc
    try:
        path = shortest_path(start.line.end_node, dest.line.start_node, geo_tool, linefilter, maxlen=maxlen)
        debug("Returning %s", path)
        return Route(start, path, dest, geo_tool)
    except LRPathNotFoundError:
        debug("No path found between these nodes")
        return None


def match_tail(current: LocationReferencePoint,
               candidates: List[Candidate],
               tail: List[LocationReferencePoint],
               reader: MapReader,
               config: Config,
               observer: Optional[DecoderObserver],
               geo_tool: GeoTool,
               depth: int = 0,
               cache: Dict[Tuple[LocationReferencePoint,Candidate], Optional[List[Route]]] = {}
) -> List[Route]:
    """Searches for the rest of the line location.

    Every element of `candidates` is routed to every candidate for `tail[0]` (best scores first).
    Actually not _every_ element, just as many as it needs until some path matches the DNP.

    Args:
        current:
            The LRP with which this part of the line location reference starts.
        candidates:
            The Candidates for the current LRP
        tail:
            The LRPs following the current.

            Contains at least one LRP, as any route has two ends.
        reader:
            The map reader on which we are operating. Needed for nominating next candidates.
        config:
            The wanted behaviour, as configuration options
        observer:
            The optional decoder observer, which emits events and calls back.
        geo_tool:
            A reference to an instance of GeoTool that understands the map's CRS

    Returns:
        If any candidate pair matches, the function calls itself for the rest of `tail` and
        returns the resulting list of routes.

    Raises:
        LRDecodeError:
            If no candidate pair matches or a recursive call can not resolve a route.
    """
    if len(candidates) == 1 and (depth, candidates[0]) in cache:
        v = cache[(current, candidates[0])]
        if v is None:
            raise LRDecodeError("Decoding was unsuccessful: No candidates left or available.")
        else:
            return v

    last_lrp = len(tail) == 1
    # The accepted distance to next point. This helps to save computations and filter bad paths
    minlen = (1 - config.max_dnp_deviation) * current.dnp - config.tolerated_dnp_dev
    maxlen = (1 + config.max_dnp_deviation) * current.dnp + config.tolerated_dnp_dev
    lfrc = config.tolerated_lfrc[current.lfrcnp]

    # Generate all pairs of candidates for the first two lrps
    next_lrp = tail[0]
    debug("Attempting to find route between lrps %s and %s via line %s",
          depth,
          depth+1,
          candidates[0].line.line_id)
    next_candidates = list(nominate_candidates(next_lrp, reader, config, observer, last_lrp, geo_tool))
    if not next_candidates:
        if observer is not None:
            observer.on_no_candidates_found(next_lrp)
        msg = f"No candidates found for LRP {next_lrp}"
        debug(msg)
        raise LRDecodeError(msg)
    elif observer is not None:
        observer.on_candidates_found(next_lrp, next_candidates)

    pairs = list(product(candidates, next_candidates))
    # Sort by line scores
    pairs.sort(key=lambda pair: (pair[0].score + pair[1].score), reverse=True)

    # For every pair of candidates, search for a path matching our requirements
    for (c_from, c_to) in pairs:
        if (c_from, c_to) in cache:
            v = cache[(c_from, c_to)]
            if v is None:
                raise LRDecodeError("Decoding was unsuccessful: No candidates left or available.")
            else:
                debug("Returning cached route")
                return v
        route = handleCandidatePair((current, next_lrp), (c_from, c_to), observer, lfrc, minlen, maxlen, geo_tool)
        if route is None:
            cache[(c_from,c_to)] = None
            continue
        if last_lrp:
            return [route]
        try:
            full_route = [route] + match_tail(next_lrp, [c_to], tail[1:], reader, config, observer, geo_tool, depth+1, cache)
            if len(candidates) == 1:
                cache[(current,candidates[0])] = full_route
            return full_route
        except LRDecodeError:
            debug("Recursive call to resolve remaining path had no success")
            continue

    if observer is not None:
        observer.on_matching_fail(current, next_lrp, candidates, next_candidates, "No candidate pair matches")
    if len(candidates) == 1:
        cache[(current, candidates[0])] = None
    raise LRDecodeError("Decoding was unsuccessful: No candidates left or available.")


def handleCandidatePair(lrps: Tuple[LocationReferencePoint, LocationReferencePoint],
                        candidates: Tuple[Candidate, Candidate], observer: Optional[DecoderObserver], lowest_frc: FRC,
                        minlen: float, maxlen: float, geo_tool: GeoTool) -> Optional[Route]:
    """
    Try to find an adequate route between two LRP candidates.

    Args:
        lrps:
            The two LRPs
        candidates:
            The two candidates
        observer:
            An optional decoder observer
        lowest_frc:
            The lowest acceptable FRC for a line to be considered part of the route
        minlen:
            The lowest acceptable route length in meters
        maxlen:
            The highest acceptable route length in meters
        geo_tool:
            A reference to an instance of GeoTool that understands the candidates' CRS

    Returns:
        If a route can not be found or has no acceptable length, None is returned.
        Else, this function returns the found route.
    """
    current, next_lrp = lrps
    source, dest = candidates
    route = get_candidate_route(source, dest, lowest_frc, maxlen, geo_tool)

    if not route:
        debug("No path for candidate found")
        if observer is not None:
            observer.on_route_fail(current, next_lrp, source, dest, "No path for candidate found")
        return None

    length = route.length()

    if observer is not None:
        observer.on_route_success(current, next_lrp, source, dest, route)

    debug("DNP should be %.02fm, is %.02fm.", current.dnp, length)
    # If the path does not match DNP, continue with the next candidate pair
    if length < minlen or length > maxlen:
        debug("Shortest path deviation from DNP is too large")
        if observer is not None:
            observer.on_route_fail_length(current, next_lrp, source, dest, route, length, minlen, maxlen)
            observer.on_route_fail(current, next_lrp, source, dest, "Shortest path deviation from DNP is too large")
        return None

    debug("Taking route %s.", route)

    return route


def is_valid_node(node: Node):
    """
    Checks if a node is a valid node. A valid node is a node that corresponds to a real-world junction
    """
    return not is_invalid_node(node)


def is_invalid_node(node: Node):
    """
    Checks if a node is an invalid node. An invalid node is a node along a road and not at a real-world junction.
    """

    # Get a list of all incoming lines to the node
    incoming_lines = list(node.incoming_lines())

    # Get a list of all outgoing lines from the node
    outgoing_lines = list(node.outgoing_lines())

    # Check the number of incoming and outgoing lines
    if (len(incoming_lines) == 1 and len(outgoing_lines) == 1) or (
            len(incoming_lines) == 2 and len(outgoing_lines) == 2):
        # Get the unique nodes of all incoming and outgoing lines
        unique_nodes = set()

        for line in incoming_lines:
            unique_nodes.add(line.start_node)
            unique_nodes.add(line.end_node)

        for line in outgoing_lines:
            unique_nodes.add(line.start_node)
            unique_nodes.add(line.end_node)

        # If it is an invalid node, there should be 3 unique nodes
        return len(unique_nodes) == 3

    else:
        # Otherwise it is a valid node
        return False
