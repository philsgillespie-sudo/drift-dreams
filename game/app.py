"""The application: window, main loop and the wiring between the game's parts."""
import gc
from collections import deque

import pygame

from core import EventBus
from input import InputManager, actions
from iso import IsoCamera
from lighting import CarLamps, DayNightCycle, LightingRenderer, StreetLamps
from sound import SoundManager
from world import World

from . import config
from .assets import Assets
from .events import Message
from .feedback import Feedback
from .render import Hud, MenuView, Popups, Text, WorldRenderer
from .scenes import DriveScene, MenuScene
from .session import Session

SMOOTHING = 4     # frames the step time is averaged over


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
    def __init__(self, start_hour=config.START_HOUR, vsync=True):
        SoundManager.pre_init()
        pygame.init()
        pygame.display.set_caption("Drift Dreams")
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
        self.camera = IsoCamera(size)
        self.session = Session(self.assets, self.world, self.bus, DayNightCycle(start_hour), self.camera)
        self.feedback = Feedback(self.bus, self.session.player, self.sound, self.camera, self.input.rumble)
        self.popups = Popups(self.bus)
        lighting = LightingRenderer(size, [StreetLamps(), CarLamps()])
        self.renderer = WorldRenderer(self.assets, self.world, self.session, lighting)
        self.hud = Hud(self.screen, self.text, self.world, self.session, self.input, self.popups)
        self.menu = MenuView(self.screen, self.text, self.assets.player_stacks)

        self.paints = list(config.PLAYER_PAINTS)
        self.paint = 0
        self.started = False
        self.autopilot = None    # tests can drive the player with a function(game) -> DriveControls
        self.scenes = {s.name: s for s in (MenuScene(), DriveScene())}
        self.scene = None
        self.change_scene("menu")

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
        self.scene = self.scenes[name]
        self.scene.enter(self)

    def cycle_paint(self, step):
        self.paint = (self.paint + step) % len(self.paints)
        self.session.player.stack = self.assets.player_stacks[self.paints[self.paint]]

    @property
    def state(self):
        return self.scene.name

    @property
    def time(self):
        return self.session.time

    @property
    def score(self):
        return self.session.combo.score

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
            pending += self.input.handle_event(e)
        pending += self.input.poll_actions()
        for action in pending:
            if not self.on_action(action):
                return False
        for notice in self.input.take_notices():
            self.bus.publish(Message(notice))
        return True

    def on_action(self, action):
        """Returns False to quit."""
        if action in (actions.TIME_BACK, actions.TIME_FWD):
            self.session.daynight.skip(1 if action == actions.TIME_FWD else -1)
            return True
        return self.scene.on_action(self, action)

    def update(self, dt):
        scene, s = self.scene, self.session
        self.sound.update(dt, s.player, s.traffic.cars, listening=scene.listening)
        scene.update(self, dt)
        s.update(dt, scene.controls(self), scene.time_speed)
        self.popups.update(dt)
        self.camera.update(dt)
        scene.move_camera(self, dt)

    def draw(self):
        self.renderer.draw(self.screen, self.camera)
        self.scene.draw_overlay(self)
