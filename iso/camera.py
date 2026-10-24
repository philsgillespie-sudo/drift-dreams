import random

import pygame
from pygame.math import Vector2 as V

ZOOM = 2   # screen pixels per world unit along the iso x axis; sprites are drawn at this resolution


def iso(p):
    """World point (units on the ground) to un-scrolled screen pixels in the 2:1 iso view."""
    return V((p[0] - p[1]) * ZOOM, (p[0] + p[1]) / 2 * ZOOM)


class IsoCamera:
    """Follows a world point and projects the world into a fixed-size view surface."""

    def __init__(self, view_size):
        self.w, self.h = view_size
        self.pos = V()
        self.shake = 0.0
        self.ox = self.oy = 0

    def jump_to(self, p):
        self.pos = V(p)

    def pan(self, target, dt, rate=1.5):
        self.pos += (V(target) - self.pos) * min(1.0, dt * rate)

    def follow(self, target, vel, dt):
        """Chase `target`, leading it in its direction of travel."""
        lead = vel * 0.35
        if lead.length() > 140:
            lead.scale_to_length(140)
        self.pos += (target + lead - self.pos) * min(1.0, dt * 5)

    def add_shake(self, amount):
        self.shake = max(self.shake, amount)

    def update(self, dt):
        self.shake = max(0.0, self.shake - dt * 25)

    def begin(self):
        """Fix this frame's scroll, including shake."""
        c = iso(self.pos)
        ox, oy = c.x - self.w / 2, c.y - self.h / 2
        if self.shake > 0:
            ox += random.uniform(-1, 1) * self.shake * ZOOM
            oy += random.uniform(-1, 1) * self.shake * ZOOM
        self.ox, self.oy = int(ox), int(oy)
        self.view = pygame.Rect(self.ox, self.oy, self.w, self.h)

    def to_screen(self, p, z=0.0):
        return V((p[0] - p[1]) * ZOOM - self.ox, ((p[0] + p[1]) / 2 - z) * ZOOM - self.oy)

    def to_world(self, sx, sy):
        x, y = (sx + self.ox) / ZOOM, (sy + self.oy) / ZOOM
        return V(y + x / 2, y - x / 2)

    def visible(self, p, margin=60):
        """`margin` is in world-scale pixels (it grows with ZOOM)."""
        s = self.to_screen(p)
        m = margin * ZOOM
        return -m < s.x < self.w + m and -m < s.y < self.h + m * 2
