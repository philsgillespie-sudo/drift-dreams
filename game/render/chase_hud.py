"""The chase's heads-up display, over the drive's: your part, the score and clock, the bust and getaway
meters, what just happened, and an arrow to the other car while it's off screen."""
import pygame
from pygame.math import Vector2 as V

from ..chase import HeadStart, MatchResult, Pursuit, RoundResult
from ..config import COP, ROBBER, ROLE_COLORS, SCREEN_H, SCREEN_W
from ..events import BUSTED

WHITE, SOFT = (255, 255, 255), (220, 220, 240)
BUST_COLOR, GETAWAY_COLOR = (255, 80, 90), (110, 240, 130)
BAR_W, BAR_H = 220, 10
ROLE_LINES = {COP: ("COP", "bust the robber"), ROBBER: ("ROBBER", "lose the cop")}
EDGE = 40               # how far in from the screen's edge the arrow sits
UNITS_PER_METRE = 6     # a car is 30 units, about 5 m
BIG_Y = 0.66            # the big line's height on screen (as a share of it): under the car, which sits mid-screen


class ChaseHud:
    def __init__(self, text):
        self.text = text
        self.panel = pygame.Surface((260, 62), pygame.SRCALPHA)
        self.panel.fill((10, 0, 30, 130))
        self.phase_drawers = {
            HeadStart: self._head_start,
            Pursuit: self._pursuit,
            RoundResult: self._round_result,
            MatchResult: self._match_result,
        }

    def draw(self, scr, player, chase):
        """`player`'s chase HUD on their screen `scr` (drawn straight after their view, so their camera is current)."""
        self.scr = scr
        self._role(player, chase)
        self._score(chase)
        drawer = self.phase_drawers.get(type(chase.phase))
        if drawer:
            drawer(player, chase, chase.phase)
        self._pointer(player, chase.other(player), chase)

    def _say(self, s, size, color, pos, anchor="center"):
        self.text.draw(s, size, color, pos, anchor, dst=self.scr)

    # -- always there ----------------------------------------------------------
    def _role(self, player, chase):
        role = chase.role_of(player)
        name, goal = ROLE_LINES[role]
        self.scr.blit(self.panel, (12, 58))
        self._say(name, "mid", ROLE_COLORS[role], (24, 62), "topleft")
        self._say(goal, "small", SOFT, (24, 104), "topleft")

    def _score(self, chase):
        a, b = chase.wins
        self._say(f"P1  {a} - {b}  P2", "normal", WHITE, (SCREEN_W / 2, 16), "midtop")
        self._say(f"ROUND {chase.round}", "small", SOFT, (SCREEN_W / 2, 44), "midtop")

    def _bar(self, y, label, value, color):
        x = SCREEN_W / 2 - BAR_W / 2
        pygame.draw.rect(self.scr, (0, 0, 0), (x - 2, y - 2, BAR_W + 4, BAR_H + 4))
        pygame.draw.rect(self.scr, color, (x, y, round(BAR_W * value), BAR_H))
        self._say(label, "small", color, (x - 8, y + BAR_H / 2), "midright")

    def _pointer(self, player, other, chase):
        """An arrow at the edge of the screen toward `other`, while they're off it."""
        s = player.camera.to_screen(other.car.pos)
        centre = V(SCREEN_W / 2, SCREEN_H / 2)
        d = s - centre
        half_w, half_h = SCREEN_W / 2 - EDGE, SCREEN_H / 2 - EDGE
        if abs(d.x) < half_w and abs(d.y) < half_h or d.length_squared() < 1:
            return
        tip = centre + d * min(half_w / abs(d.x) if d.x else 1e9, half_h / abs(d.y) if d.y else 1e9)
        u = d.normalize()
        side = V(-u.y, u.x) * 11
        points = [tip, tip - u * 22 + side, tip - u * 22 - side]
        color = ROLE_COLORS[chase.role_of(other)]
        pygame.draw.polygon(self.scr, (0, 0, 0), points, 0)
        pygame.draw.polygon(self.scr, color, [tip - u * 3, tip - u * 19 + side * 0.7, tip - u * 19 - side * 0.7], 0)
        metres = round(player.car.pos.distance_to(other.car.pos) / UNITS_PER_METRE, -1)
        self._say(f"{metres:.0f} m", "small", color, tip - u * 40)

    # -- per phase -------------------------------------------------------------
    def _head_start(self, player, chase, phase):
        cop = chase.role_of(player) == COP
        self._say(str(max(1, int(phase.left) + 1)), "big", WHITE, (SCREEN_W / 2, SCREEN_H * BIG_Y))
        self._say("hold it... they're getting away" if cop else "GO! get a head start",
                  "normal", SOFT, (SCREEN_W / 2, SCREEN_H * BIG_Y + 60))

    def _pursuit(self, player, chase, phase):
        left = int(phase.left + 0.999)
        self._say(f"{left // 60}:{left % 60:02d}", "mid", WHITE if left > 10 else BUST_COLOR,
                  (SCREEN_W / 2, 66), "midtop")
        y = 116
        for label, meter, color in (("BUST", phase.bust, BUST_COLOR), ("GETAWAY", phase.getaway, GETAWAY_COLOR)):
            if meter.value > 0:
                self._bar(y, label, meter.value, color)
                y += 22

    def _round_result(self, player, chase, phase):
        busted = phase.how == BUSTED
        color = ROLE_COLORS[chase.role_of(phase.winner)]
        self._say("BUSTED!" if busted else "GOT AWAY!", "big", color, (SCREEN_W / 2, SCREEN_H * BIG_Y))
        self._say(f"PLAYER {phase.winner.index + 1} TAKES THE ROUND", "normal", SOFT,
                  (SCREEN_W / 2, SCREEN_H * BIG_Y + 60))

    def _match_result(self, player, chase, phase):
        won = phase.winner is player
        self._say("YOU WIN!" if won else "YOU LOSE", "big", (255, 214, 60) if won else BUST_COLOR,
                  (SCREEN_W / 2, SCREEN_H * BIG_Y))
        self._say("START / ENTER: rematch     BACK / ESC: menu", "normal", SOFT,
                  (SCREEN_W / 2, SCREEN_H * BIG_Y + 60))
