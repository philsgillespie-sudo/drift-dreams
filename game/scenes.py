"""Game states. The active scene decides what the players' input means, who steers the cars, how the
cameras move and what is drawn over the world. A new mode is a new Scene."""
import math

from pygame.math import Vector2 as V

from input import DriveControls, actions

from . import config
from .chase import Chase

PARKED = DriveControls(handbrake=True)
HINT_TIME = 8         # seconds the controls hint shows after a drive starts


class Scene:
    name = ""
    time_speed = 1.0      # how fast the day goes by
    listening = True      # whether the car sounds play

    def enter(self, game):
        pass

    def exit(self, game):
        pass

    def players_changed(self, game):
        """A player joined or left."""
        pass

    def on_action(self, game, slot, action):
        """slot: the input slot it came from (player index; may be a player not playing yet).
        Returns False to quit."""
        return True

    def update(self, game, dt):
        pass

    def controls(self, game):
        """One DriveControls per player."""
        return [PARKED] * len(game.players)

    def move_camera(self, game, dt):
        pass

    def draw_overlay(self, game, dst, player):
        """Draw over `player`'s view, on their window's surface `dst`."""
        pass


class MenuScene(Scene):
    """The title screen: the city drives itself behind a paint picker while the day spins by.
    Two players start a chase; one on their own goes for a free drive."""
    name = "menu"
    time_speed = config.MENU_TIME_SPEED
    listening = False

    def __init__(self):
        self.t = 0.0

    def on_action(self, game, slot, action):
        players = game.players
        if action == actions.JOIN:
            game.sound.play("ui_confirm" if len(players) == 1 else "ui_back")
            game.add_player() if len(players) == 1 else game.remove_player()
            return True
        if slot >= len(players):
            # a device nobody plays with yet: its start button joins
            if action in (actions.CONFIRM, actions.SELECT):
                game.sound.play("ui_confirm")
                game.add_player()
            return True
        if action == actions.BACK:
            if slot == 0:
                return False
            game.sound.play("ui_back")
            game.remove_player()
        elif action in (actions.LEFT, actions.RIGHT):
            game.cycle_paint(players[slot], -1 if action == actions.LEFT else 1)
            game.sound.play("ui_click")
        elif action in (actions.CONFIRM, actions.SELECT):
            game.sound.play("ui_confirm")
            game.change_scene("chase" if len(players) > 1 else "drive")
        return True

    def update(self, game, dt):
        self.t += dt

    def move_camera(self, game, dt):
        a = self.t * 0.15
        for p in game.players:
            p.camera.pan(p.car.pos + V(math.cos(a), math.sin(a)) * 160, dt)

    def draw_overlay(self, game, dst, player):
        game.menu.draw(dst, self.t, game.paints, player.paint, game.input.device_name(player.slot),
                       player.index, len(game.players))


class DriveScene(Scene):
    """A free drive round the city, no rules: what one player gets on their own."""
    name = "drive"

    def __init__(self):
        self.t = 0.0

    def enter(self, game):
        self.t = 0.0

    def on_action(self, game, slot, action):
        if slot >= len(game.players):
            return True
        player = game.players[slot]
        if action == actions.BACK:
            game.sound.play("ui_back")
            game.change_scene("menu")
        elif action == actions.RESET:
            game.session.to_road(player)
        elif action == actions.RESTART:
            game.sound.play("ui_confirm")
            game.session.to_start(player)
        return True

    def update(self, game, dt):
        self.t += dt

    def controls(self, game):
        pilots = (game.autopilot, game.autopilot2)
        return [pilots[p.index](game) if pilots[p.index] else game.input.drive(p.slot) for p in game.players]

    def move_camera(self, game, dt):
        for p in game.players:
            p.camera.follow(p.car.pos, p.car.vel, dt)

    def draw_overlay(self, game, dst, player):
        game.hud.draw(dst, player, game.popups[player.index], self.t < HINT_TIME)


class ChaseScene(DriveScene):
    """Cops and robbers between two players (see game.chase). Driving is as in the free drive; the
    chase decides who is held, and its HUD goes over the drive's."""
    name = "chase"

    def __init__(self, livery, hud):
        """livery: the chase.Livery that dresses the cars; hud: the render.ChaseHud."""
        super().__init__()
        self.livery, self.hud = livery, hud
        self.chase = None

    def enter(self, game):
        super().enter(game)
        self.chase = Chase(game.bus, game.session)

    def exit(self, game):
        self.chase.detach()
        self.chase = None
        self.livery.restore(game.players)

    def players_changed(self, game):
        if len(game.players) < 2:
            game.change_scene("menu")       # a chase needs two

    def on_action(self, game, slot, action):
        if slot >= len(game.players):
            return True
        if action == actions.BACK:
            game.sound.play("ui_back")
            game.change_scene("menu")
        elif action == actions.RESET:
            game.session.to_road(game.players[slot])   # stuck: back onto the nearest road
        elif action in (actions.CONFIRM, actions.SELECT) and self.chase.rematch():
            game.sound.play("ui_confirm")
        return True

    def update(self, game, dt):
        super().update(game, dt)
        self.chase.update(dt)

    def controls(self, game):
        driven = super().controls(game)
        return [PARKED if self.chase.held(p) else c for p, c in zip(game.players, driven)]

    def draw_overlay(self, game, dst, player):
        chase = self.chase
        colors = [config.ROLE_COLORS[chase.role_of(p)] for p in game.players]
        game.hud.draw(dst, player, game.popups[player.index], self.t < HINT_TIME, colors)
        self.hud.draw(dst, player, chase)
