"""The application: windows, main loop and the wiring between the game's parts.

Player 1 plays in the main window; a second player gets a window of their own (render.SecondWindow),
on the second monitor when there is one. Two players play cops and robbers (scenes.ChaseScene).
"""
import gc
from collections import deque

import pygame

from core import EventBus
from input import InputManager, actions
from lighting import CarLamps, DayNightCycle, LightingRenderer, Sirens, StreetLamps
from sound import SoundManager
from world import World

from . import config
from .assets import Assets
from .chase import Announcer, Livery
from .events import Message
from .feedback import Feedback
from .render import ChaseHud, Hud, MenuView, Popups, SecondWindow, Text, WorldRenderer
from .scenes import ChaseScene, DriveScene, MenuScene
from .session import Session

SMOOTHING = 4     # frames the step time is averaged over
TITLE = "Cops & Robbers"


class FrameTimer:
    """Step time for the simulation. Frame times jitter by a millisecond or two even when every
    frame makes the refresh, and stepping by the raw time shows that jitter as judder; averaging
    the last few frames evens it out without slowing the game down."""

    def __init__(self, cap):
        self.clock = pygame.time.Clock()
        self.cap = cap
        self.recent = deque(maxlen=SMOOTHING)

    def tick(self):
        self.recent.append(min(self.clock.tick(self.cap) / 1000.0, config.MAX_DT))
        return sum(self.recent) / len(self.recent)


class Game:
    def __init__(self, start_hour=config.START_HOUR, vsync=True, players=1):
        SoundManager.pre_init()
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen, self.vsync = self._open_window(vsync)
        self.timer = FrameTimer(config.MAX_FPS if self.vsync else config.FPS)
        self.text = Text(self.screen)

        self._loading_screen("Loading...")
        self.input = InputManager()
        self.sound = SoundManager(config.SFX)
        self.assets = Assets(progress=self._loading_screen)
        self._loading_screen("Building the city...")
        self.world = World(self.assets.district_art, self.assets.decos)

        size = (config.SCREEN_W, config.SCREEN_H)
        self.bus = EventBus()
        self.session = Session(self.assets, self.world, self.bus, DayNightCycle(start_hour), size)
        self.feedback = Feedback(self.bus, self.session.players, self.sound, self.input.rumble)
        self.announcer = Announcer(self.bus, self.sound, self.input.rumble)
        lighting = LightingRenderer(size, [StreetLamps(), CarLamps(), Sirens()])
        self.renderer = WorldRenderer(self.assets, self.world, self.session, lighting)
        self.hud = Hud(self.text, self.world, self.session, self.input)
        self.menu = MenuView(self.text, self.assets.player_stacks)
        self.popups = [Popups(self.bus, self.session.player)]   # one per player's screen
        self.second = None       # player 2's window, while there is a player 2

        self.paints = list(config.PLAYER_PAINTS)
        livery = Livery(self.bus, self.assets.police_stack, self.paint_stack)
        # tests can drive the players with functions(game) -> DriveControls
        self.autopilot = None
        self.autopilot2 = None
        self.scenes = {s.name: s for s in (MenuScene(), DriveScene(), ChaseScene(livery, ChaseHud(self.text)))}
        self.scene = None
        self.change_scene("menu")
        if players > 1:
            self.add_player()

        # everything loaded so far lives for the whole game: keep the garbage collector off it,
        # so its sweeps stay short and don't land as dropped frames
        gc.collect()
        gc.freeze()

    @staticmethod
    def _open_window(vsync):
        """(display surface, whether vsync is on). Vsync paces frames to the monitor, which is what
        makes motion smooth; it needs the SCALED renderer, so fall back to a plain window."""
        size = (config.SCREEN_W, config.SCREEN_H)
        if vsync:
            try:
                return pygame.display.set_mode(size, pygame.SCALED, vsync=1), True
            except pygame.error:
                pass
        return pygame.display.set_mode(size), False

    def _loading_screen(self, msg):
        self.screen.fill((24, 22, 34))
        self.text.draw(msg, "mid", (240, 220, 255), (config.SCREEN_W / 2, config.SCREEN_H / 2), "center", False)
        pygame.display.flip()
        pygame.event.pump()

    # -- state ---------------------------------------------------------------------
    def change_scene(self, name):
        if self.scene is not None:
            self.scene.exit(self)
        self.scene = self.scenes[name]
        self.scene.enter(self)

    def paint_stack(self, player):
        """The car sprites in the paint this player picked."""
        return self.assets.player_stacks[self.paints[player.paint]]

    def cycle_paint(self, player, step):
        player.paint = (player.paint + step) % len(self.paints)
        player.car.stack = self.paint_stack(player)

    @property
    def players(self):
        return self.session.players

    def add_player(self):
        """Player 2 joins, in a window of their own."""
        if len(self.players) > 1:
            return
        player = self.session.add_player()
        self.popups.append(Popups(self.bus, player.car))
        self.second = SecondWindow((config.SCREEN_W, config.SCREEN_H), f"{TITLE} - Player 2")
        self.input.players = 2
        self.scene.players_changed(self)

    def remove_player(self):
        if len(self.players) < 2:
            return
        self.session.remove_player()
        self.popups.pop().detach()
        self.second.close()
        self.second = None
        self.input.players = 1
        self.scene.players_changed(self)

    @property
    def state(self):
        return self.scene.name

    @property
    def time(self):
        return self.session.time

    @property
    def paint(self):
        return self.players[0].paint

    @property
    def daynight(self):
        return self.session.daynight

    # -- main loop -------------------------------------------------------------
    def run(self):
        while True:
            dt = self.timer.tick()
            if not self.handle_events():
                return
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def handle_events(self):
        pending = []
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            if e.type == pygame.WINDOWCLOSE and getattr(e, "window", None) is not None:
                if self.second is not None and e.window.id == self.second.id:
                    self.remove_player()    # closing player 2's window: they leave
                    continue
                return False                # closing the main window quits
            pending += self.input.handle_event(e)
        pending += self.input.poll_actions()
        for slot, action in pending:
            if not self.on_action(slot, action):
                return False
        for notice in self.input.take_notices():
            self.bus.publish(Message(notice))
        return True

    def on_action(self, slot, action):
        """slot: whose device it came from. Returns False to quit."""
        if action in (actions.TIME_BACK, actions.TIME_FWD):
            self.session.daynight.skip(1 if action == actions.TIME_FWD else -1)
            return True
        return self.scene.on_action(self, slot, action)

    def update(self, dt):
        scene, s = self.scene, self.session
        self.sound.update(dt, s.player_cars, s.traffic.cars, listening=scene.listening)
        scene.update(self, dt)
        s.update(dt, scene.controls(self), scene.time_speed)
        for popups in self.popups:
            popups.update(dt)
        for p in self.players:
            p.camera.update(dt)
        scene.move_camera(self, dt)

    def draw(self):
        # Every view is drawn on the main window's surface: player 2's first, handed to their window,
        # then player 1's. The ground chunks are RLE surfaces, which SDL re-encodes whenever one is
        # blitted to a different surface than last time, so two target surfaces would cost a
        # re-encode per chunk per view.
        for player in reversed(self.players):
            self.renderer.draw(self.screen, player.camera, player.car)
            self.scene.draw_overlay(self, self.screen, player)
            if player.index:
                self.second.present(self.screen)
        self.world.end_frame([p.camera for p in self.players])
