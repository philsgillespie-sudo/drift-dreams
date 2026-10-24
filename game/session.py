"""The running open world: the players' cars, traffic, props and effects, stepped once a frame.

The session is the same behind the title screen and the drive; scenes only change what steers the
players, how fast the clock runs and whether moves score. One or two players share it.
"""
import math

from pygame.math import Vector2 as V

from car import Car
from core import SpatialHash
from iso import IsoCamera
from traffic import Traffic

from . import config
from .collisions import Collisions
from .combo import Combo
from .effects import Particles, TyreEffects
from .events import PlayerPlaced
from .players import Player
from .props import PropSystem

GRID_CELL = 64
JOIN_BEHIND = 80        # how far behind player 1 a joining player 2 is put


class Session:
    def __init__(self, assets, world, bus, daynight, view_size):
        self.assets, self.world, self.bus, self.daynight = assets, world, bus, daynight
        self.view_size = view_size
        self.traffic = Traffic(assets.traffic_stacks, world.parked, world.roads, count=config.TRAFFIC_COUNT)
        self.grid = SpatialHash(GRID_CELL)
        self.collisions = Collisions(world, bus)
        self.props = PropSystem(world.prop_spots, world, bus)
        self.particles = Particles(bus)
        self.tyres = TyreEffects(world, self.particles)
        self.players = []
        self.player_cars = []
        self.scoring = False     # whether drifts, near misses and smashes count
        self.time = 0.0
        self.add_player()

    @property
    def player(self):
        """Player 1's car."""
        return self.players[0].car

    @property
    def combo(self):
        return self.players[0].combo

    @property
    def camera(self):
        return self.players[0].camera

    def add_player(self):
        """A new player: player 1 at the start, player 2 on the road just behind player 1."""
        index = len(self.players)
        paint = list(config.PLAYER_PAINTS)[index]
        car = Car(self.world.start, math.pi / 2, self.assets.player_stacks[paint])
        player = Player(index, car, Combo(self.bus, self.daynight, car), IsoCamera(self.view_size))
        self.players.append(player)
        self.player_cars = [p.car for p in self.players]
        if index == 0:
            player.camera.jump_to(car.pos)
        else:
            lead = self.players[0].car
            pos, heading = self.world.nearest_road(lead.pos - lead.fwd() * JOIN_BEHIND)
            if abs(math.remainder(heading - lead.heading, math.tau)) > math.pi / 2:
                heading += math.pi
            self.place(player, pos, heading)
        return player

    def remove_player(self):
        """The last player leaves (player 1 always stays)."""
        if len(self.players) > 1:
            self.players.pop().combo.detach()
            self.player_cars = [p.car for p in self.players]

    def cars(self):
        return self.player_cars + self.traffic.all()

    def update(self, dt, controls, time_speed=1.0):
        """controls: one DriveControls per player."""
        self.time += dt
        dn, traffic, players = self.daynight, self.traffic, self.player_cars
        dn.update(dt, time_speed)
        traffic.set_density(config.NIGHT_TRAFFIC if dn.is_night else 1.0)
        for car, c in zip(players, controls):
            car.update(dt, c.throttle, c.brake, c.steer, c.handbrake)

        self.grid.rebuild(self.cars())
        traffic.update(dt, players, [p.camera for p in self.players], self.grid)
        everyone = self.cars()
        self.grid.rebuild(everyone)
        self.collisions.update(everyone, self.grid)
        world = self.world
        for car in everyone:
            car.surface = world.surface_at(car.pos)
            car.on_kerb = world.on_sidewalk(car.pos)

        for car in players:
            self.tyres.update(car)
        for car in traffic.cars:
            if car.drifting or car.dazed > 0:
                self.tyres.update(car)
        self.props.update(dt, players, self.grid, self.scoring)
        if self.scoring:
            for p in self.players:
                p.combo.update(dt, traffic.cars)
        self.particles.update(dt)

    # -- putting a player somewhere ------------------------------------------------
    def place(self, player, pos, heading):
        p = player.car
        p.pos, p.heading = V(pos), heading
        p.vel, p.angvel, p.drifting, p.prev_wheels = V(), 0.0, False, None
        player.camera.jump_to(p.pos)
        self.bus.publish(PlayerPlaced(p))

    def to_road(self, player=None):
        player = player or self.players[0]
        pos, heading = self.world.nearest_road(player.car.pos)
        # face whichever way along the road is closer to where the car points
        if abs(math.remainder(heading - player.car.heading, math.tau)) > math.pi / 2:
            heading += math.pi
        self.place(player, pos, heading)

    def to_start(self, player=None):
        player = player or self.players[0]
        pos = V(self.world.start)
        if player.index:
            pos -= V(JOIN_BEHIND, 0)    # behind player 1's start (heading pi/2 faces +x), not on top of it
        self.place(player, pos, math.pi / 2)
