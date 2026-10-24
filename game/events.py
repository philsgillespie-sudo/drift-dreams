"""What happens in a drive or a chase, published on the core.EventBus for whichever systems care."""
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
    """A player smashed a prop (once per prop)."""
    prop: Any
    car: Any               # the player's car that did it


@dataclass
class Crashed:
    """A player crashed hard."""
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


# -- the chase: these carry Players (game.players.Player), not cars -----------
@dataclass
class RoundStarted:
    """A round of the chase begins; the cop is held for the head start."""
    number: int            # 1, 2, ...
    cop: Any
    robber: Any


@dataclass
class Countdown:
    """A second of the head start ticked by; 0 means the cop is let go."""
    seconds: int


@dataclass
class RoundOver:
    winner: Any
    loser: Any
    how: str               # BUSTED, TIME_UP or LOST


BUSTED, TIME_UP, LOST = "busted", "time up", "lost"


@dataclass
class MatchOver:
    winner: Any
    loser: Any
