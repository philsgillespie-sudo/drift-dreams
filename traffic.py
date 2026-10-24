"""Traffic: AI cars keeping to the right-hand lanes of the street grid, plus parked cars."""
import math
import random

from pygame.math import Vector2 as V

from car import Car, heading_of, wrap_angle
from city import BLOCKS, EDGE, LANE, PITCH, T, node_pos

DIRS = [V(1, 0), V(0, 1), V(-1, 0), V(0, -1)]
APPROACH = 56          # waypoint distance from an intersection's centre
TURN_SPEED = 80
SPAWN_NEAR, SPAWN_FAR, DESPAWN = 500, 1100, 1400


def right_of(d):
    return V(-d.y, d.x)


def bezier(a, c, b, t):
    return a * (1 - t) ** 2 + c * 2 * t * (1 - t) + b * t * t


class TrafficCar(Car):
    def __init__(self, stack, rng):
        super().__init__(V(), 0.0, stack)
        self.rng = rng
        self.path = []          # [(point, speed)]
        self.node = (0, 0)
        self.dir = 0
        self.cruise = 160
        self.dazed = 0.0
        self.wait = 0.0         # time spent stopped behind something
        self.pushy = 0.0        # ignores the car in front for a moment after waiting too long
        self.stuck = 0.0
        self.near_miss_t = 0.0

    # -- planning ------------------------------------------------------------
    def place(self, a, b, d):
        """Put the car in the lane leaving node (a, b) in direction d, somewhere along the block."""
        dv = DIRS[d]
        start = node_pos(a, b)
        self.pos = start + dv * self.rng.uniform(70, PITCH * T - 70) + right_of(dv) * LANE
        self.heading = heading_of(dv)
        self.cruise = self.rng.uniform(130, 185)
        self.vel = dv * self.cruise * 0.8
        self.angvel = self.steer = 0.0
        self.drifting = False
        self.dazed = self.wait = self.pushy = self.stuck = 0.0
        self.node = (a + int(dv.x), b + int(dv.y))
        self.dir = d
        self.path = [(self._approach(self.node, dv), self.cruise)]

    def _approach(self, node, dv):
        return node_pos(*node) - dv * APPROACH + right_of(dv) * LANE

    @staticmethod
    def valid(node):
        return 0 <= node[0] <= BLOCKS and 0 <= node[1] <= BLOCKS

    def _plan_turn(self):
        """At the current node: pick a way on and queue the waypoints through the junction."""
        d = self.dir
        options = []
        for nd, w in ((d, 2.0), ((d + 1) % 4, 1.0), ((d + 3) % 4, 1.0)):
            nxt = (self.node[0] + int(DIRS[nd].x), self.node[1] + int(DIRS[nd].y))
            if self.valid(nxt):
                options += [nd] * int(w * 2)
        if not options:
            nd = (d + 2) % 4   # dead end at the edge of the map: U-turn
        else:
            nd = self.rng.choice(options)
        dv, nv = DIRS[d], DIRS[nd]
        b = node_pos(*self.node)
        entry = b - dv * APPROACH + right_of(dv) * LANE
        exit_ = b + nv * APPROACH + right_of(nv) * LANE
        if nd == d:
            self.path.append((exit_, self.cruise))
        else:
            # corner where the two lane lines cross, as a Bezier control point
            if nd == (d + 2) % 4:
                corner = b + dv * APPROACH * 0.6
            else:
                corner = b + right_of(dv) * LANE + dv * (LANE if nd == (d + 3) % 4 else -LANE)
            for t in (0.35, 0.7, 1.0):
                self.path.append((bezier(entry, corner, exit_, t), TURN_SPEED))
        self.node = (self.node[0] + int(nv.x), self.node[1] + int(nv.y))
        self.dir = nd
        self.path.append((self._approach(self.node, nv), self.cruise))

    def replan(self):
        """After being knocked about: head for the next junction in the way it's facing."""
        f = self.fwd()
        d = max(range(4), key=lambda k: DIRS[k].dot(f))
        fx = (self.pos.x / T - EDGE - 1.5) / PITCH
        fy = (self.pos.y / T - EDGE - 1.5) / PITCH
        dv = DIRS[d]
        a = math.floor(fx) + 1 if dv.x > 0 else math.ceil(fx) - 1 if dv.x < 0 else round(fx)
        b = math.floor(fy) + 1 if dv.y > 0 else math.ceil(fy) - 1 if dv.y < 0 else round(fy)
        node = (min(BLOCKS, max(0, a)), min(BLOCKS, max(0, b)))
        self.node, self.dir = node, d
        self.path = [(self._approach(node, dv), self.cruise)]

    # -- driving ---------------------------------------------------------------
    def drive(self, dt, others):
        if self.dazed > 0:
            self.dazed -= dt
            self.update(dt, 0, 0, 0, True)
            if self.dazed <= 0:
                self.replan()
            return
        if not self.path:
            self._plan_turn()
        target, want = self.path[0]
        to = target - self.pos
        if to.length() < 16 or (to.length() < 40 and to.dot(self.fwd()) < 0):
            self.path.pop(0)
            if len(self.path) < 2:
                self._plan_turn()
            target, want = self.path[0]
            to = target - self.pos
        diff = wrap_angle(heading_of(to) - self.heading)
        steer = max(-1.0, min(1.0, diff * 2.5))
        if abs(diff) > 1.2:
            want = min(want, 60)

        # keep a gap to whatever is ahead
        speed = self.vel.length()
        f = self.fwd()
        r = right_of(f)
        blocked = False
        if self.pushy <= 0:
            for o in others:
                if o is self:
                    continue
                rel = o.pos - self.pos
                ahead = rel.dot(f)
                if 0 < ahead < 90 and abs(rel.dot(r)) < 20:
                    want = min(want, max(0.0, (ahead - 32) * 2.5))
                    blocked = True
        else:
            self.pushy -= dt
        if blocked and speed < 10:
            self.wait += dt
            if self.wait > 3.0:
                self.wait, self.pushy = 0.0, 1.5
        else:
            self.wait = 0.0

        throttle = max(0.0, min(1.0, (want - speed) / 30))
        brake = 1.0 if speed > want + 25 or (want < 5 and speed > 5) else 0.0
        if brake and speed < 15:
            brake = 0.0   # don't let the brake turn into reverse
        self.update(dt, throttle, brake, steer, want < 5 and speed < 15)

        if speed < 8 and not blocked:
            self.stuck += dt
        else:
            self.stuck = 0.0


class ParkedCar(Car):
    """Sits in its bay until something shoves it."""

    def drive(self, dt, others):
        self.update(dt, 0, 0, 0, True)


class Traffic:
    def __init__(self, stacks, parked_spots, count=28, seed=3):
        self.rng = random.Random(seed)
        self.stacks = stacks
        self.pool = [TrafficCar(self.rng.choice(stacks), self.rng) for _ in range(count)]
        self.cars = list(self.pool)   # the ones on the road; the rest wait off the map
        self.parked = [ParkedCar(p, h, self.rng.choice(stacks)) for p, h in parked_spots]
        self.density = 1.0
        self._spawned = False

    def all(self):
        return self.cars + self.parked

    def set_density(self, share):
        """Share of the pool to keep on the road. Cars join and leave out of sight, one a frame."""
        self.density = max(0.0, min(1.0, share))

    def _balance(self, player, cam):
        want = round(len(self.pool) * self.density)
        if len(self.cars) > want:
            for car in self.cars:
                if not cam.visible(car.pos, 80):
                    self.cars.remove(car)
                    break
        elif len(self.cars) < want:
            car = next(c for c in self.pool if c not in self.cars)
            if self.spawn(car, player.pos, cam):
                self.cars.append(car)

    def spawn(self, car, player_pos, cam, near=SPAWN_NEAR, far=SPAWN_FAR):
        for _ in range(40):
            a, b = self.rng.randint(0, BLOCKS), self.rng.randint(0, BLOCKS)
            d = self.rng.randrange(4)
            nxt = (a + int(DIRS[d].x), b + int(DIRS[d].y))
            if not TrafficCar.valid(nxt):
                continue
            car.place(a, b, d)
            dist = car.pos.distance_to(player_pos)
            if not near <= dist <= far or (cam is not None and cam.visible(car.pos, 80)):
                continue
            if any(o is not car and o.pos.distance_to(car.pos) < 70 for o in self.cars):
                continue
            return True
        return False

    def update(self, dt, player, cam):
        if not self._spawned:
            for car in self.cars:
                self.spawn(car, player.pos, cam, 120, SPAWN_FAR)
            self._spawned = True
        self._balance(player, cam)
        everyone = self.cars + self.parked + [player]
        for car in self.cars:
            far = car.pos.distance_to(player.pos) > DESPAWN
            if far or (car.stuck > 4 and not cam.visible(car.pos, 80)):
                self.spawn(car, player.pos, cam)
                continue
            near = [o for o in everyone if o is not car and abs(o.pos.x - car.pos.x) < 100
                    and abs(o.pos.y - car.pos.y) < 100]
            car.drive(dt, near)
            car.near_miss_t = max(0.0, car.near_miss_t - dt)
        for car in self.parked:
            if car.vel.length_squared() > 1:
                car.drive(dt, ())
