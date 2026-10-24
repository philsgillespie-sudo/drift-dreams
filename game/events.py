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
    """The player smashed a prop hard enough to score it (once per prop)."""
    prop: Any


@dataclass
class Crashed:
    """The player crashed hard: the combo is lost."""


@dataclass
class PlayerPlaced:
    """The player was put back somewhere (onto the road, or the start)."""


@dataclass
class Message:
    """A line of text popping up over the drive."""
    text: str
    color: tuple = (200, 200, 255)
