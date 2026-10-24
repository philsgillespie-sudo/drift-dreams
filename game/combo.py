"""Scoring: drifts, near misses and smashes build a combo, banked once the chain runs out."""
import math

from car import CAR_RADIUS

from . import config
from .events import CarsCollided, Crashed, Message, PlayerPlaced, PropSmashed

CHAIN = 1.4              # seconds a combo stays alive after the last scoring move
MAX_MULT = 8
NEAR_MISS_SPEED = 200
NEAR_MISS_GAP = 14       # how close (beyond touching) counts as a near miss
NEAR_MISS_POINTS = 150
NEAR_MISS_COOLDOWN = 3.0
DRIFT_SPEED = 100
DRIFT_SLIP = 0.15


class Combo:
    """One player's combo; the events it hears are filtered to that player's car."""

    def __init__(self, bus, daynight, player):
        self.bus, self.daynight, self.player = bus, daynight, player
        self.score = 0
        self.best = 0
        self.pending = 0.0
        self.mult = 1
        self.chain = 0.0
        self.was_drifting = False
        self.cooldowns = {}    # traffic car -> seconds until it can be near-missed again
        self._handlers = [(PropSmashed, self._on_smash), (Crashed, self._on_crash),
                          (PlayerPlaced, self._on_placed), (CarsCollided, self._on_cars)]
        for event_type, handler in self._handlers:
            bus.subscribe(event_type, handler)

    def detach(self):
        """Stop listening (the player left)."""
        for event_type, handler in self._handlers:
            self.bus.unsubscribe(event_type, handler)

    def add(self, pts, msg=None, color=(120, 220, 255)):
        self.pending += pts
        self.chain = max(self.chain, CHAIN)
        if msg:
            self.bus.publish(Message(msg, color, self.player))

    def lose(self, msg):
        if msg and self.pending > 0:
            self.bus.publish(Message(msg, (255, 90, 90), self.player))
        self.pending = 0.0
        self.mult = 1
        self.chain = 0.0

    def _on_smash(self, e):
        if e.car is self.player:
            pts = e.prop.type.points
            self.add(pts, f"+{pts} SMASH", (255, 180, 90))

    def _on_crash(self, e):
        if e.car is self.player:
            self.lose("CRASHED - COMBO LOST")

    def _on_placed(self, e):
        if e.car is self.player:
            self.lose(None)

    def _on_cars(self, e):
        if self.player in (e.a, e.b):
            other = e.b if e.a is self.player else e.a
            self.cooldowns[other] = NEAR_MISS_COOLDOWN   # a hit is not a near miss

    def update(self, dt, traffic):
        cool = self.cooldowns
        for car, t in list(cool.items()):
            if t > dt:
                cool[car] = t - dt
            else:
                del cool[car]
        self._near_misses(traffic)
        self._drift(dt)

    def _near_misses(self, traffic):
        p = self.player
        if p.vel.length() < NEAR_MISS_SPEED:
            return
        cool = self.cooldowns
        for car in traffic:
            if car in cool:
                continue
            d = car.pos.distance_to(p.pos)
            if 2 * CAR_RADIUS < d < 2 * CAR_RADIUS + NEAR_MISS_GAP:
                cool[car] = NEAR_MISS_COOLDOWN
                self.add(NEAR_MISS_POINTS, f"+{NEAR_MISS_POINTS} NEAR MISS")

    def _drift(self, dt):
        p = self.player
        speed = p.vel.length()
        drifting = p.drifting and speed > DRIFT_SPEED and abs(p.slip) > DRIFT_SLIP
        if drifting and p.surface != "road":
            self.lose("OFF ROAD - COMBO LOST")
            drifting = False
        if drifting:
            if not self.was_drifting and self.chain > 0:
                self.mult = min(MAX_MULT, self.mult + 1)
            self.pending += abs(math.degrees(p.slip)) * speed * 0.08 * dt
            self.chain = CHAIN
        elif self.chain > 0:
            self.chain -= dt
            if self.chain <= 0 and self.pending > 0:
                self._bank()
        self.was_drifting = drifting

    def _bank(self):
        night = self.daynight.is_night
        pts = int(self.pending * self.mult * (config.NIGHT_BONUS if night else 1))
        self.score += pts
        self.best = max(self.best, pts)
        self.bus.publish(Message(f"+{pts}" + (f"  x{self.mult}" if self.mult > 1 else "")
                                 + ("  NIGHT" if night else ""), (120, 255, 140), self.player))
        self.pending = 0.0
        self.mult = 1
