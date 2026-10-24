"""Engine-level helpers with no game knowledge: event bus, spatial hashing."""
from .events import EventBus
from .spatial import SpatialHash

__all__ = ["EventBus", "SpatialHash"]
