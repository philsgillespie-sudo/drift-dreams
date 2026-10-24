"""Street furniture that gets knocked about: cones, hydrants, bins.

A new kind of prop is one PROP_TYPES entry (plus its stack in props_stack); nothing else changes.
"""
import math
import random
from dataclasses import dataclass

from pygame.math import Vector2 as V

from car import CAR_RADIUS

from .events import PropKnocked, PropSmashed

ACTIVE_RANGE = 900     # props further than this from every player are left alone
SMASH_SPEED = 60       # a player must be at least this fast to score a smash


@dataclass(frozen=True)
class PropType:
    radius: float
    points: int            # combo points for smashing it
    keep: float            # share of its speed a car keeps when it ploughs through one
    sprays: bool = False   # bursts into a fountain when smashed


PROP_TYPES = {
    "cone": PropType(radius=5, points=40, keep=0.97),
    "hydrant": PropType(radius=5, points=120, keep=0.85, sprays=True),
    "bin": PropType(radius=6, points=60, keep=0.85),
}


class Prop:
    def __init__(self, kind, pos):
        self.kind = kind
        self.type = PROP_TYPES[kind]
        self.radius = self.type.radius
        self.home = V(pos)
        self.pos = V(pos)
        self.vel = V()
        self.angle = random.uniform(0, 360)
        self.spin = 0.0
        self.hit = False


class PropSystem:
    def __init__(self, spots, world, bus):
        self.world, self.bus = world, bus
        self.props = [Prop(k, p) for k, p in spots]

    def update(self, dt, players, grid, scoring):
        """players: the players' cars. grid: core.SpatialHash of the cars. scoring: whether smashes
        count toward the combo."""
        near = [(p.pos.x, p.pos.y) for p in players]
        for prop in self.props:
            x, y = prop.pos
            if all(abs(x - px) > ACTIVE_RANGE or abs(y - py) > ACTIVE_RANGE for px, py in near):
                continue
            lim = CAR_RADIUS + prop.radius
            for car in grid.near(prop.pos, lim):
                if car.parked:
                    continue
                d = prop.pos - car.pos
                dist = d.length()
                if 0 < dist < lim:
                    n = d / dist
                    prop.pos = car.pos + n * lim
                    prop.vel = car.vel * 1.1 + n * 80
                    prop.spin = random.uniform(-720, 720)
                    speed = car.vel.length()
                    self.bus.publish(PropKnocked(prop, car, speed))
                    car.vel *= prop.type.keep
                    if car in players and not prop.hit and speed > SMASH_SPEED and scoring:
                        prop.hit = True
                        self.bus.publish(PropSmashed(prop, car))
            if prop.vel.length_squared() > 1:
                prop.pos += prop.vel * dt
                prop.vel *= math.exp(-2.5 * dt)
                prop.angle += prop.spin * dt
                prop.spin *= math.exp(-2.5 * dt)
                res = self.world.collide(prop.pos, prop.radius)
                if res:
                    prop.pos += res[0]
                    prop.vel = prop.vel.reflect(res[1]) * 0.5
