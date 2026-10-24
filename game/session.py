"""The running open world: the player's car, traffic, props and effects, stepped once a frame.

The session is the same behind the title screen and the drive; scenes only change what steers the
player, how fast the clock runs and whether moves score.
"""
import math

from pygame.math import Vector2 as V

from car import Car
from core import SpatialHash
from traffic import Traffic

from . import config
from .collisions import Collisions
from .combo import Combo
from .effects import Particles, TyreEffects
from .events import PlayerPlaced
from .props import PropSystem

GRID_CELL = 64


class Session:
    def __init__(self, assets, world, bus, daynight, camera):
        self.world, self.bus, self.daynight, self.camera = world, bus, daynight, camera
        self.player = Car(world.start, math.pi / 2, assets.player_stacks["red"])
        self.traffic = Traffic(assets.traffic_stacks, world.parked, world.roads, count=config.TRAFFIC_COUNT)
        self.grid = SpatialHash(GRID_CELL)
        self.collisions = Collisions(world, bus)
        self.props = PropSystem(world.prop_spots, world, bus)
        self.particles = Particles(bus)
        self.tyres = TyreEffects(world, self.particles)
        self.combo = Combo(bus, daynight, self.player)
        self.scoring = False     # whether drifts, near misses and smashes count
        self.time = 0.0
        camera.jump_to(self.player.pos)

    def cars(self):
        return [self.player] + self.traffic.all()

    def update(self, dt, controls, time_speed=1.0):
        self.time += dt
        dn, p, traffic = self.daynight, self.player, self.traffic
        dn.update(dt, time_speed)
        traffic.set_density(config.NIGHT_TRAFFIC if dn.is_night else 1.0)
        p.update(dt, controls.throttle, controls.brake, controls.steer, controls.handbrake)

        self.grid.rebuild(self.cars())
        traffic.update(dt, p, self.camera, self.grid)
        everyone = self.cars()
        self.grid.rebuild(everyone)
        self.collisions.update(everyone, self.grid)
        world = self.world
        for car in everyone:
            car.surface = world.surface_at(car.pos)
            car.on_kerb = world.on_sidewalk(car.pos)

        self.tyres.update(p)
        for car in traffic.cars:
            if car.drifting or car.dazed > 0:
                self.tyres.update(car)
        self.props.update(dt, p, self.grid, self.scoring)
        if self.scoring:
            self.combo.update(dt, traffic.cars)
        self.particles.update(dt)

    # -- putting the player somewhere ----------------------------------------------
    def place_player(self, pos, heading):
        p = self.player
        p.pos, p.heading = V(pos), heading
        p.vel, p.angvel, p.drifting, p.prev_wheels = V(), 0.0, False, None
        self.camera.jump_to(p.pos)
        self.bus.publish(PlayerPlaced())

    def to_road(self):
        pos, heading = self.world.nearest_road(self.player.pos)
        # face whichever way along the road is closer to where the car points
        if abs(math.remainder(heading - self.player.heading, math.tau)) > math.pi / 2:
            heading += math.pi
        self.place_player(pos, heading)

    def to_start(self):
        self.place_player(self.world.start, math.pi / 2)
