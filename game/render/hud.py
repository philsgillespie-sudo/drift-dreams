"""The drive's heads-up display: clock, minimap, speed, the controls and pop-up messages.
What a game mode adds (render.ChaseHud) is drawn over it."""
import math

import pygame
from pygame.math import Vector2 as V

from ..config import SCREEN_H, SCREEN_W
from ..events import Message

POPUP_LIFE = 1.8
POPUPS_SHOWN = 4


class Popups:
    """Recent Message events for one player's screen, each shown for POPUP_LIFE seconds."""

    def __init__(self, bus, car):
        self.bus, self.car = bus, car
        self.items = []    # [text, colour, age]
        bus.subscribe(Message, self._on_message)

    def _on_message(self, e):
        if e.car is None or e.car is self.car:
            self.items.append([e.text, e.color, 0.0])

    def detach(self):
        self.bus.unsubscribe(Message, self._on_message)

    def update(self, dt):
        for pop in self.items:
            pop[2] += dt
        self.items = [pop for pop in self.items if pop[2] < POPUP_LIFE]


PLAYER_DOTS = ((255, 80, 160), (80, 220, 255))   # each player's dot on the minimap, unless a mode says otherwise
PANEL = (12, 12, 260, 40)


class Hud:
    def __init__(self, text, world, session, inputs):
        self.text, self.world, self.session, self.inputs = text, world, session, inputs
        self.panel = pygame.Surface(PANEL[2:], pygame.SRCALPHA)
        self.panel.fill((10, 0, 30, 130))

    def draw(self, scr, player, popups, show_hint, colors=PLAYER_DOTS):
        """One player's HUD on their screen `scr`; popups: their Popups. colors: each player's colour by index."""
        self.scr = scr
        s = self.session
        p = player.car
        text = lambda *a, **k: self.text.draw(*a, dst=scr, **k)  # noqa: E731
        scr.blit(self.panel, PANEL[:2])
        if len(s.players) > 1:
            text(f"P{player.index + 1}", "normal", colors[player.index], (264, 20), "topright")
        self.draw_clock((24, 22))
        self.draw_minimap(player, colors)

        kmh = int(p.vel.length() * 0.6)
        text(f"{kmh:3d}", "mid", (255, 255, 255), (24, SCREEN_H - 92))
        text("km/h", "small", (200, 200, 220), (110, SCREEN_H - 76))

        for k, (txt, col, age) in enumerate(popups.items[-POPUPS_SHOWN:]):
            y = SCREEN_H * 0.3 - age * 30 + k * 32
            text(txt, "normal", col, (SCREEN_W / 2, y), "center")

        if show_hint:
            text(self.inputs.hint(player.slot), "small", (240, 240, 240), (SCREEN_W / 2, SCREEN_H - 30), "center")

    def draw_minimap(self, player, colors):
        scr, world, s = self.scr, self.world, self.session
        mm = world.minimap
        offset = V(SCREEN_W - mm.get_width() - 12, 12)
        scr.blit(mm, offset)
        for car in s.traffic.cars:
            q = world.minimap_pos(car.pos) + offset
            scr.fill((230, 230, 240), (q.x, q.y, 2, 2))
        # the other player under this one's dot
        for other in sorted(s.players, key=lambda o: o is player):
            q = world.minimap_pos(other.car.pos) + offset
            pygame.draw.circle(scr, (0, 0, 0), q, 5)
            pygame.draw.circle(scr, colors[other.index], q, 4)

    def draw_clock(self, pos):
        """Time of day with a sun or moon."""
        scr, dn = self.scr, self.session.daynight
        c = (pos[0] + 8, pos[1] + 9)
        if dn.is_night:
            pygame.draw.circle(scr, (235, 235, 255), c, 7)
            pygame.draw.circle(scr, (10, 0, 30), (c[0] + 4, c[1] - 2), 6)   # bite out a crescent
        else:
            pygame.draw.circle(scr, (255, 214, 60), c, 6)
            for k in range(8):
                a = k * math.pi / 4
                pygame.draw.line(scr, (255, 214, 60), (c[0] + math.cos(a) * 8, c[1] + math.sin(a) * 8),
                                 (c[0] + math.cos(a) * 10, c[1] + math.sin(a) * 10), 2)
        self.text.draw(dn.label(), "small", (230, 230, 250), (pos[0] + 24, pos[1]), dst=scr)
