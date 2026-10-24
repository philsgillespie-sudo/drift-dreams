"""Cars against the world and against each other. Reports impacts as events; what they mean (sound,
shake, rams in a chase) is up to the systems listening."""
import random

from car import CAR_RADIUS

from .events import CarsCollided, WallHit

DAZE_IMPACT = 80     # traffic hit harder than this loses the plot for a moment
DAZE_TIME = 1.6


class Collisions:
    def __init__(self, world, bus):
        self.world, self.bus = world, bus

    def update(self, cars, grid):
        """cars: every car; grid: a core.SpatialHash of them."""
        self._against_world(cars)
        self._against_each_other(cars, grid)

    def _against_world(self, cars):
        for car in cars:
            if car.parked and car.vel.length_squared() < 1:
                continue
            res = self.world.collide(car.pos, CAR_RADIUS)
            if res is None:
                continue
            corr, n, kind = res
            car.pos += corr
            vn = car.vel.dot(n)
            if vn < 0:
                car.vel -= n * vn * 1.4
                car.vel *= 0.8
                car.angvel += random.uniform(-1, 1) * min(2.0, -vn / 150)
                self.bus.publish(WallHit(car, -vn))

    def _against_each_other(self, cars, grid):
        order = {car: k for k, car in enumerate(cars)}
        reach = 2 * CAR_RADIUS
        for k, a in enumerate(cars):
            for b in grid.near(a.pos, reach):
                if order.get(b, -1) <= k:
                    continue    # each pair once, and never a car with itself
                if abs(a.pos.x - b.pos.x) > reach or abs(a.pos.y - b.pos.y) > reach:
                    continue
                d = b.pos - a.pos
                dist = d.length()
                if not 0 < dist < reach:
                    continue
                n = d / dist
                push = (reach - dist) / 2
                a.pos -= n * push
                b.pos += n * push
                rel = (b.vel - a.vel).dot(n)
                if rel < 0:
                    imp = n * rel * 0.75
                    a.vel += imp
                    b.vel -= imp
                    for c in (a, b):
                        c.angvel += random.uniform(-1, 1) * min(2.0, -rel / 100)
                        if hasattr(c, "dazed") and -rel > DAZE_IMPACT:
                            c.dazed = DAZE_TIME
                    self.bus.publish(CarsCollided(a, b, -rel))
