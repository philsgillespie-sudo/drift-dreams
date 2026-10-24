"""Traffic: AI cars keeping to the right-hand lanes of the road network, plus parked cars.

Cars only know the roads.RoadGraph, so they drive every district's roads alike.
"""
import random

from pygame.math import Vector2 as V

from car import Car, heading_of, wrap_angle

LANE = 24              # lane centre's offset from the road's centre line
APPROACH = 56          # waypoint distance from an intersection's centre
TURN_SPEED = 80
SPAWN_NEAR, SPAWN_FAR, DESPAWN = 500, 1100, 1400
LOOK_AHEAD = 100       # how far round itself a car looks for traffic


def right_of(d):
    return V(-d.y, d.x)


def bezier(a, c, b, t):
    return a * (1 - t) ** 2 + c * 2 * t * (1 - t) + b * t * t


def lane_crossing(b, dv, nv):
    """Where the lane into junction b (travelling dv) crosses the lane out of it (travelling nv)."""
    r1, r2 = right_of(dv) * LANE, right_of(nv) * LANE
    rhs = r2 - r1
    det = nv.x * dv.y - dv.x * nv.y
    t = (nv.x * rhs.y - rhs.x * nv.y) / det
    return b + r1 + dv * t


class TrafficCar(Car):
    def __init__(self, stack, rng, roads):
        super().__init__(V(), 0.0, stack)
        self.rng = rng
        self.roads = roads
        self.path = []          # [(point, speed)]
        self.prev = self.node = None   # the junction behind and the one ahead
        self.dv = V(1, 0)       # direction of the road being driven
        self.cruise = 160
        self.dazed = 0.0
        self.wait = 0.0         # time spent stopped behind something
        self.pushy = 0.0        # ignores the car in front for a moment after waiting too long
        self.stuck = 0.0
        self.near_miss_t = 0.0

    # -- planning ------------------------------------------------------------
    def place(self, a, b):
        """Put the car in the lane from junction a toward b, somewhere along the road."""
        pa, pb = self.roads.pos(a), self.roads.pos(b)
        dv = (pb - pa).normalize()
        self.pos = pa + dv * self.rng.uniform(70, max(70.0, pa.distance_to(pb) - 70)) + right_of(dv) * LANE
        self.heading = heading_of(dv)
        self.cruise = self.rng.uniform(130, 185)
        self.vel = dv * self.cruise * 0.8
        self.angvel = self.steer = 0.0
        self.drifting = False
        self.dazed = self.wait = self.pushy = self.stuck = 0.0
        self.prev, self.node, self.dv = a, b, dv
        self.path = [(self._approach(b, dv), self.cruise)]

    def _approach(self, node, dv):
        return self.roads.pos(node) - dv * APPROACH + right_of(dv) * LANE

    def _plan_turn(self):
        """At the junction ahead: pick a way on and queue the waypoints through it."""
        roads, node, dv = self.roads, self.node, self.dv
        b = roads.pos(node)
        options, weights = [], []
        for n in roads.neighbours(node):
            if n == self.prev:
                continue
            nv = (roads.pos(n) - b).normalize()
            options.append((n, nv))
            weights.append(2.0 if nv.dot(dv) > 0.7 else 1.0)   # straight on is likelier than turning
        if options:
            n, nv = self.rng.choices(options, weights)[0]
        else:
            n, nv = self.prev, -dv   # dead end: U-turn
        entry = b - dv * APPROACH + right_of(dv) * LANE
        exit_ = b + nv * APPROACH + right_of(nv) * LANE
        turn = nv.dot(dv)
        if turn > 0.99:
            self.path.append((exit_, self.cruise))
        else:
            # corner where the two lane lines cross, as a Bezier control point
            corner = b + dv * APPROACH * 0.6 if turn < -0.99 else lane_crossing(b, dv, nv)
            for t in (0.35, 0.7, 1.0):
                self.path.append((bezier(entry, corner, exit_, t), TURN_SPEED))
        self.prev, self.node, self.dv = node, n, nv
        self.path.append((self._approach(n, nv), self.cruise))

    def replan(self):
        """After being knocked about: head for the next junction on the road it's facing along."""
        a, b = self.roads.edge_ahead(self.pos, self.fwd())
        self.prev, self.node = a, b
        self.dv = (self.roads.pos(b) - self.roads.pos(a)).normalize()
        self.path = [(self._approach(b, self.dv), self.cruise)]

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
    parked = True

    def drive(self, dt, others):
        self.update(dt, 0, 0, 0, True)


class Traffic:
    def __init__(self, stacks, parked_spots, roads, count=28, seed=3):
        self.rng = random.Random(seed)
        self.stacks = stacks
        self.edges = roads.directed_edges()
        self.pool = [TrafficCar(self.rng.choice(stacks), self.rng, roads) for _ in range(count)]
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
            car.place(*self.rng.choice(self.edges))
            dist = car.pos.distance_to(player_pos)
            if not near <= dist <= far or (cam is not None and cam.visible(car.pos, 80)):
                continue
            if any(o is not car and o.pos.distance_to(car.pos) < 70 for o in self.cars):
                continue
            return True
        return False

    def update(self, dt, player, cam, grid):
        """grid: a core.SpatialHash of every car, for finding the traffic round each one."""
        if not self._spawned:
            for car in self.cars:
                self.spawn(car, player.pos, cam, 120, SPAWN_FAR)
            self._spawned = True
            grid.rebuild([player] + self.cars + self.parked)
        self._balance(player, cam)
        for car in self.cars:
            far = car.pos.distance_to(player.pos) > DESPAWN
            if far or (car.stuck > 4 and not cam.visible(car.pos, 80)):
                self.spawn(car, player.pos, cam)
                continue
            p = car.pos
            near = [o for o in grid.near(p, LOOK_AHEAD) if o is not car
                    and abs(o.pos.x - p.x) < LOOK_AHEAD and abs(o.pos.y - p.y) < LOOK_AHEAD]
            car.drive(dt, near)
            car.near_miss_t = max(0.0, car.near_miss_t - dt)
        for car in self.parked:
            if car.vel.length_squared() > 1:
                car.drive(dt, ())
