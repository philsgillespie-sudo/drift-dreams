"""Particles (tyre smoke, hydrant spray) and the skid marks sliding cars leave on the ground."""
import math
import random

from pygame.math import Vector2 as V

from .events import PropSmashed

MAX_SMOKE = 300
SPRAY_TIME = 6.0
SKID_COLORS = {"road": (34, 34, 40), "grass": (70, 100, 45)}
SKID_DEFAULT = (150, 120, 80)


class Smoke:
    __slots__ = ("pos", "vel", "age", "life", "z")

    def __init__(self, pos, vel, life=0.9):
        self.pos, self.vel = V(pos), V(vel)
        self.age, self.life, self.z = 0.0, life, 0.0


class Drop:
    """A droplet from a burst hydrant."""
    __slots__ = ("pos", "vel", "z", "vz", "age")

    def __init__(self, pos, vel, vz):
        self.pos, self.vel, self.z, self.vz, self.age = V(pos), V(vel), 4.0, vz, 0.0


class Particles:
    def __init__(self, bus):
        self.smoke, self.drops, self.sprays = [], [], []
        bus.subscribe(PropSmashed, self._on_smash)

    def _on_smash(self, e):
        if e.prop.type.sprays:
            self.sprays.append([V(e.prop.home), SPRAY_TIME])

    def puff(self, pos, vel):
        if len(self.smoke) < MAX_SMOKE:
            self.smoke.append(Smoke(pos, vel))

    def update(self, dt):
        drag = math.exp(-1.5 * dt)
        for s in self.smoke:
            s.age += dt
            s.pos += s.vel * dt
            s.vel *= drag
            s.z += 8 * dt
        self.smoke = [s for s in self.smoke if s.age < s.life]
        for spray in self.sprays:
            spray[1] -= dt
            for _ in range(3):
                a = random.uniform(0, math.tau)
                self.drops.append(Drop(spray[0], V(math.cos(a), math.sin(a)) * random.uniform(5, 25),
                                       random.uniform(60, 110)))
        self.sprays = [s for s in self.sprays if s[1] > 0]
        for d in self.drops:
            d.age += dt
            d.pos += d.vel * dt
            d.vz -= 220 * dt
            d.z += d.vz * dt
        self.drops = [d for d in self.drops if d.z > 0 and d.age < 2]


class TyreEffects:
    """Skid marks (baked into the world's ground) and smoke from cars sliding about."""

    def __init__(self, world, particles):
        self.world, self.particles = world, particles

    def update(self, car):
        speed = car.vel.length()
        sliding = (car.drifting and speed > 60) or (abs(car.slip) > 0.2 and speed > 100)
        wheels = car.rear_wheels()
        if sliding and car.prev_wheels:
            col = SKID_COLORS.get(car.surface, SKID_DEFAULT)
            for a, b in zip(car.prev_wheels, wheels):
                self.world.add_skid(V(a), V(b), col)
        car.prev_wheels = wheels if sliding else None
        if sliding and len(self.particles.smoke) < MAX_SMOKE and random.random() < 0.6:
            if car.surface == "road" or random.random() < 0.3:
                w = random.choice(wheels)
                self.particles.puff(w, car.vel * 0.15 + V(random.uniform(-15, 15), random.uniform(-15, 15)))
