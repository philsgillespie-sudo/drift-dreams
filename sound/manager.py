import glob
import os
import re
import weakref

import pygame
from pygame.math import Vector2 as V

from .engine import IDLE_RPM, EngineVoice, target_rpm

MASTER = 0.55      # headroom so loops plus one-shots don't clip the mix
HEARING = 750      # world units: sounds from elsewhere in the city fade out over this distance
PAN_WIDTH = 450    # screen px either side of the listener for full pan
LOOP_CHANNELS = 8  # reserved for the loops below; one-shots get the rest
MAX_VOICES = 2     # copies of one clip allowed at once (e.g. several cars crashing together)


def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


class Loop:
    """A clip looping forever on its own channel; only its volume changes."""

    def __init__(self, channel, sound):
        self.channel, self.volume = channel, 0.0
        if sound is not None:
            channel.play(sound, loops=-1)
        channel.set_volume(0.0, 0.0)

    def fade_to(self, target, dt, rate=10.0):
        self.volume += (target - self.volume) * min(1.0, rate * dt)
        self.channel.set_volume(self.volume * MASTER, self.volume * MASTER)


class _CarState:
    __slots__ = ("rpm", "throttle")

    def __init__(self):
        self.rpm = float(IDLE_RPM)
        self.throttle = 0.0  # smoothed: the AI's pedal is on/off


class SoundManager:
    """Game-facing audio.

    Cars are duck-typed: anything with pos, vel, throttle, slip, drifting,
    surface and on_kerb works. Call update() once a frame;
    it runs the player's engine, tyre and surface loops and the nearest rival's
    engine. Call play() for other events. Everything is a no-op if no audio device could be opened.
    """

    @staticmethod
    def pre_init():
        """Call before pygame.init() for a small mixer buffer (low latency)."""
        pygame.mixer.pre_init(44100, -16, 2, 512)

    def __init__(self, sfx_dir):
        self.enabled = pygame.mixer.get_init() is not None
        self.sounds = {}
        self.listener = None
        self.cars = weakref.WeakKeyDictionary()
        self.engine_vol = [0.0, 0.0]  # player, rival
        if not self.enabled:
            return
        ladder = []
        for path in sorted(glob.glob(os.path.join(sfx_dir, "*.ogg"))):
            name = os.path.splitext(os.path.basename(path))[0]
            m = re.fullmatch(r"engine_(\d+)_loop", name)
            if m:
                ladder.append((int(m.group(1)), pygame.mixer.Sound(path)))
            else:
                self.sounds[name] = pygame.mixer.Sound(path)
        ladder.sort(key=lambda rung: rung[0])

        pygame.mixer.set_num_channels(32)
        pygame.mixer.set_reserved(LOOP_CHANNELS)
        ch = [pygame.mixer.Channel(i) for i in range(LOOP_CHANNELS)]
        self.engines = [EngineVoice(ch[0:2], ladder), EngineVoice(ch[2:4], ladder)] if len(ladder) > 1 else []
        self.screech = Loop(ch[4], self.sounds.get("tire_screech_loop"))
        self.gravel = Loop(ch[5], self.sounds.get("gravel_loop"))
        self.grass = Loop(ch[6], self.sounds.get("grass_loop"))
        self.kerb = Loop(ch[7], self.sounds.get("kerb_rumble_loop"))

    def _spatial(self, pos):
        """(left, right) gains for a sound at pos, heard from the listener."""
        if self.listener is None:
            return 1.0, 1.0
        d = V(pos) - self.listener
        gain = clamp(1 - d.length() / HEARING) ** 2
        pan = clamp((d.x - d.y) / PAN_WIDTH, -1.0, 1.0)  # iso view: screen x is world x - y
        return gain * min(1.0, 1 - 0.7 * pan), gain * min(1.0, 1 + 0.7 * pan)

    def play(self, name, volume=1.0, pos=None):
        """One-shot. With pos it's attenuated and panned relative to the player."""
        snd = self.sounds.get(name) if self.enabled else None
        if snd is None or snd.get_num_channels() >= MAX_VOICES:
            return
        left, right = self._spatial(pos) if pos is not None else (1.0, 1.0)
        if left + right < 0.02:
            return
        ch = snd.play()
        if ch is not None:
            ch.set_volume(volume * left * MASTER, volume * right * MASTER)

    def update(self, dt, player, opponents, listening=True):
        """listening=False (menus) fades every loop out and skips one-shots."""
        if not self.enabled:
            return
        self.listener = V(player.pos)
        for car in [player, *opponents]:
            st = self.cars.setdefault(car, _CarState())
            speed = car.vel.length()
            st.throttle += (car.throttle - st.throttle) * min(1.0, 6 * dt)
            want = target_rpm(speed, st.throttle, car.drifting or abs(car.slip) > 0.2)
            st.rpm += (want - st.rpm) * min(1.0, (12 if want > st.rpm else 6) * dt)

        on = 1.0 if listening else 0.0
        speed = player.vel.length()
        if self.engines:
            vol = self.engine_vol
            vol[0] += ((0.65 + 0.35 * self.cars[player].throttle) * on - vol[0]) * min(1.0, 8 * dt)
            self.engines[0].update(self.cars[player].rpm, vol[0] * MASTER, vol[0] * MASTER)
            rival = min(opponents, key=lambda c: c.pos.distance_squared_to(player.pos), default=None)
            vol[1] += (0.7 * on - vol[1]) * min(1.0, 8 * dt)
            left, right = self._spatial(rival.pos) if rival is not None else (0.0, 0.0)
            rpm = self.cars[rival].rpm if rival is not None else IDLE_RPM
            self.engines[1].update(rpm, vol[1] * left * MASTER, vol[1] * right * MASTER)

        road = player.surface == "road"
        slide = clamp((abs(player.slip) - 0.12) / 0.35) * clamp((speed - 60) / 150)
        self.screech.fade_to(0.8 * slide * road * on, dt)
        moving = clamp(speed / 225)
        self.gravel.fade_to(0.9 * moving * (player.surface == "gravel") * on, dt)
        self.grass.fade_to(0.8 * moving * (player.surface == "grass") * on, dt)
        self.kerb.fade_to(0.9 * clamp(speed / 150) * player.on_kerb * on, dt, rate=20)
