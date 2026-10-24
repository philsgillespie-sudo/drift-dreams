"""What happens in a drive, published on the core.EventBus for whichever systems care."""
from dataclasses import dataclass
from typing import Any


@dataclass
class WallHit:
    car: Any
    impact: float          # speed into the wall


@dataclass
class CarsCollided:
    a: Any
    b: Any
    impact: float          # closing speed


@dataclass
class PropKnocked:
    prop: Any
    car: Any
    speed: float


@dataclass
class PropSmashed:
    """A player smashed a prop hard enough to score it (once per prop)."""
    prop: Any
    car: Any               # the player's car that did it


@dataclass
class Crashed:
    """A player crashed hard: their combo is lost."""
    car: Any


@dataclass
class PlayerPlaced:
    """A player was put back somewhere (onto the road, or the start)."""
    car: Any


@dataclass
class Message:
    """A line of text popping up over the drive."""
    text: str
    color: tuple = (200, 200, 255)
    car: Any = None        # whose screen it shows on; None for everyone
