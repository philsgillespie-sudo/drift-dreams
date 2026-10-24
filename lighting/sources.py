"""What gives off light. Each source names the glow sprites it uses and turns the visible
scene into Lights; the renderer draws them without knowing what they belong to."""
import math
import random
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from pygame.math import Vector2 as V

from iso import ZOOM

from .glow import GROUND, make_glow


@dataclass(frozen=True)
class Light:
    glow: str                # name of a glow sprite from the source's glows()
    pos: V                   # world position
    z: float = 0.0           # height above the ground, world units
    emissive: bool = False   # False: lights the ground; True: the light itself, drawn over the dark


@dataclass
class LitScene:
    """The visible things that can carry lights this frame."""
    lamps: list = field(default_factory=list)   # (pos, angle) of street lamps
    cars: list = field(default_factory=list)    # cars that are driving (parked ones stay dark)


class LightSource(Protocol):
    def glows(self) -> dict: ...

    def lights(self, scene: LitScene, darkness: float) -> Iterable[Light]: ...


class StreetLamps:
    """A pool of light under each street lamp. They switch on one by one as dusk falls,
    flickering for a moment as they catch."""
    ON_FROM, ON_SPREAD, FLICKER = 0.25, 0.25, 0.03
    REACH = 6.5      # arm length: pole to lamp head (13 sprite pixels)
    HEAD_Z = 22.5    # lamp head height (45 slices up)

    def glows(self):
        return {"lamp_pool": make_glow(70 * ZOOM, (255, 200, 120), GROUND),
                "lamp_bulb": make_glow(9 * ZOOM, (255, 235, 190))}

    def lights(self, scene, darkness):
        for pos, ang in scene.lamps:
            on_at = self.ON_FROM + hash((int(pos.x), int(pos.y))) % 100 / 100 * self.ON_SPREAD
            if darkness < on_at or (darkness < on_at + self.FLICKER and random.random() < 0.5):
                continue
            a = math.radians(ang)
            head = pos + V(math.cos(a), math.sin(a)) * self.REACH
            yield Light("lamp_pool", head)
            yield Light("lamp_bulb", head, self.HEAD_Z, emissive=True)


class CarLamps:
    """Headlights throwing a beam ahead, red tail lights behind. Drivers switch on at dusk,
    before the street lamps."""
    ON_AT = 0.15
    NOSE, TAIL, HALF_WIDTH, LAMP_Z = 14, 14, 5, 4

    def glows(self):
        return {"beam": make_glow(26 * ZOOM, (230, 235, 255), GROUND),
                "tail_pool": make_glow(10 * ZOOM, (255, 40, 30), GROUND),
                "headlamp": make_glow(4 * ZOOM, (255, 255, 230)),
                "tail_lamp": make_glow(3 * ZOOM, (255, 50, 40))}

    def lights(self, scene, darkness):
        if darkness < self.ON_AT:
            return
        for car in scene.cars:
            f = car.fwd()
            r = V(-f.y, f.x) * self.HALF_WIDTH
            # two overlapping pools make a beam that narrows ahead of the car
            yield Light("beam", car.pos + f * 28)
            yield Light("beam", car.pos + f * 50)
            yield Light("tail_pool", car.pos - f * 18)
            nose, tail = car.pos + f * self.NOSE, car.pos - f * self.TAIL
            for side in (r, -r):
                yield Light("headlamp", nose + side, self.LAMP_Z, emissive=True)
                yield Light("tail_lamp", tail + side, self.LAMP_Z, emissive=True)
