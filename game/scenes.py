"""Game states. The active scene decides what the player's input means, who steers the car, how the
camera moves and what is drawn over the world. A new mode (a race, a garage) is a new Scene."""
import math

from pygame.math import Vector2 as V

from input import DriveControls, actions

from . import config

PARKED = DriveControls(handbrake=True)


class Scene:
    name = ""
    time_speed = 1.0      # how fast the day goes by
    scoring = False       # whether moves count toward the combo
    listening = True      # whether the car sounds play

    def enter(self, game):
        game.session.scoring = self.scoring

    def on_action(self, game, action):
        """Returns False to quit."""
        return True

    def update(self, game, dt):
        pass

    def controls(self, game):
        return PARKED

    def move_camera(self, game, dt):
        pass

    def draw_overlay(self, game):
        pass


class MenuScene(Scene):
    """The title screen: the city drives itself behind a paint picker while the day spins by."""
    name = "menu"
    time_speed = config.MENU_TIME_SPEED
    listening = False

    def __init__(self):
        self.t = 0.0

    def on_action(self, game, action):
        if action == actions.BACK:
            return False
        if action in (actions.LEFT, actions.RIGHT):
            game.cycle_paint(-1 if action == actions.LEFT else 1)
            game.sound.play("ui_click")
        elif action in (actions.CONFIRM, actions.SELECT):
            game.sound.play("ui_confirm")
            game.started = True
            game.change_scene("drive")
        return True

    def update(self, game, dt):
        self.t += dt

    def move_camera(self, game, dt):
        a = self.t * 0.15
        game.camera.pan(game.session.player.pos + V(math.cos(a), math.sin(a)) * 160, dt)

    def draw_overlay(self, game):
        game.menu.draw(self.t, game.paints, game.paint, game.started, game.input.gamepad_name)


class DriveScene(Scene):
    name = "drive"
    scoring = True

    def on_action(self, game, action):
        if action == actions.BACK:
            game.sound.play("ui_back")
            game.change_scene("menu")
        elif action == actions.RESET:
            game.session.to_road()
        elif action == actions.RESTART:
            game.sound.play("ui_confirm")
            game.session.to_start()
        return True

    def controls(self, game):
        return game.autopilot(game) if game.autopilot else game.input.drive()

    def move_camera(self, game, dt):
        p = game.session.player
        game.camera.follow(p.pos, p.vel, dt)

    def draw_overlay(self, game):
        game.hud.draw(game.started)
