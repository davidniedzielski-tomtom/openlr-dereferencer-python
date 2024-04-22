#!/usr/bin/env python3
"""
OpenLR line decoder package.
"""

from .decoding import decode, Config, load_config, save_config, DEFAULT_CONFIG
from .observer import DecoderObserver, SimpleObserver
from .maps.abstract import GeoTool
from .maps.wgs84 import WGS84GeoTool

from ._version import (
    __title__,
    __description__,
    __url__,
    __version__,
    __author__,
    __author_email__,
    __license__,
)

__geo_tool__ = WGS84GeoTool()


def set_geotool(tool: GeoTool):
    global __geo_tool__
    __geo_tool__ = tool


def geotool() -> GeoTool:
    global __geo_tool__
    return __geo_tool__
