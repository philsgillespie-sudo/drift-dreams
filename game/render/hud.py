"""The drive's heads-up display: score, clock, minimap, speed, combo and pop-up messages."""
import math

import pygame
from pygame.math import Vector2 as V

from ..config import NIGHT_BONUS, SCREEN_H, SCREEN_W
from ..combo import CHAIN
from ..events import Message

POPUP_LIFE = 1.8
POPUPS_SHOWN = 4
HINT_TIME = 8


class Popups:
    """Recent Message events, each shown for POPUP_LIFE seconds."""

    def __init__(self, bus):
        self.items = []    # [text, colour, age]
        bus.subscribe(Message, lambda e: self.items.append([e.text, e.color, 0.0]))

    def update(self, dt):
        for pop in self.items:
            pop[2] += dt
        self.items = [pop for pop in self.items if pop[2] < POPUP_LIFE]


class Hud:
    def __init__(self, screen, text, world, session, inputs, popups):
        self.screen, self.text, self.world, self.session = screen, text, world, session
        self.inputs, self.popups = inputs, popups
        self.panel = pygame.Surface((260, 104), pygame.SRCALPHA)
        self.panel.fill((10, 0, 30, 130))

    def draw(self, started):
        scr, text, s = self.screen, self.text, self.session
        p, combo = s.player, s.combo
        scr.blit(self.panel, (12, 12))
        text.draw(f"SCORE {combo.score}", "normal", (255, 255, 255), (24, 20))
        text.draw(f"BEST COMBO {combo.best}", "small", (200, 200, 230), (24, 54))
        self.draw_clock((24, 82))
        self.draw_minimap()

        kmh = int(p.vel.length() * 0.6)
        text.draw(f"{kmh:3d}", "mid", (255, 255, 255), (24, SCREEN_H - 92))
        text.draw("km/h", "small", (200, 200, 220), (110, SCREEN_H - 76))

        if combo.pending > 0:
            line = f"{int(combo.pending)}"
            if combo.mult > 1:
                line += f"  x{combo.mult}"
            text.draw(line, "mid", (255, 255, 160), (SCREEN_W / 2, 18), "midtop")
            w = int(160 * max(0.0, min(1.0, combo.chain / CHAIN)))
            pygame.draw.rect(scr, (255, 255, 160), (SCREEN_W / 2 - 80, 66, w, 4))

        for k, (txt, col, age) in enumerate(self.popups.items[-POPUPS_SHOWN:]):
            y = SCREEN_H * 0.3 - age * 30 + k * 32
            text.draw(txt, "normal", col, (SCREEN_W / 2, y), "center")

        if s.time < HINT_TIME and started:
            hint = ("RT gas  LT brake  A/RB drift  Y to road" if self.inputs.has_gamepad else
                    "ARROWS/WASD drive  SPACE drift  T to road  R start")
            text.draw(hint, "small", (240, 240, 240), (SCREEN_W / 2, SCREEN_H - 30), "center")

    def draw_minimap(self):
        scr, world, s = self.screen, self.world, self.session
        mm = world.minimap
        offset = V(SCREEN_W - mm.get_width() - 12, 12)
        scr.blit(mm, offset)
        for car in s.traffic.cars:
            q = world.minimap_pos(car.pos) + offset
            scr.fill((230, 230, 240), (q.x, q.y, 2, 2))
        q = world.minimap_pos(s.player.pos) + offset
        pygame.draw.circle(scr, (0, 0, 0), q, 5)
        pygame.draw.circle(scr, (255, 80, 160), q, 4)

    def draw_clock(self, pos):
        """Time of day with a sun or moon, and the night bonus while it's on."""
        scr, dn = self.screen, self.session.daynight
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
        self.text.draw(dn.label(), "small", (230, 230, 250), (pos[0] + 24, pos[1]))
        if dn.is_night:
            self.text.draw(f"NIGHT x{NIGHT_BONUS:g}", "small", (170, 200, 255), (pos[0] + 100, pos[1]))
