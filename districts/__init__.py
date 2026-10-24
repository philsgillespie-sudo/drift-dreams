"""The world's districts and the layout that places them.

LAYOUT is built in order; each builder gets the district art and the districts built so far (by
name), so a new district can attach itself to an existing one, as the bridge does to the city.
"""
from dataclasses import dataclass

from .base import CHUNK, TILE_H, TILE_W, T, District
from .bridge import Bridge
from .city import City


@dataclass
class DistrictArt:
    tiles: dict        # ground tile name -> surface
    buildings: dict    # building frame name -> surface


LAYOUT = {
    "city": lambda art, built: City(art.tiles, art.buildings),
    "bridge": lambda art, built: Bridge(built["city"], art.tiles),
}

__all__ = ["CHUNK", "LAYOUT", "TILE_H", "TILE_W", "T", "Bridge", "City", "District", "DistrictArt"]
