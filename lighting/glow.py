"""Soft light sprites, made in code so lighting needs nothing from the sprite sheets."""
import pygame

GROUND = 0.5     # squash for a pool of light on the ground in the 2:1 iso view


def make_glow(radius, color, squash=1.0):
    """A radial gradient from `color` at the centre to black at the rim, on an opaque surface
    for additive blending. squash < 1 flattens it (GROUND lays it on the road)."""
    size = radius * 2
    s = pygame.Surface((size, size))
    for k in range(radius, 0, -1):            # big to small, so inner rings overwrite outer ones
        f = (1 - k / radius) ** 2
        pygame.draw.circle(s, [round(c * f) for c in color], (radius, radius), k)
    if squash != 1:
        s = pygame.transform.smoothscale(s, (size, max(1, round(size * squash))))
    return s.convert()


class GlowSet:
    """Named glow sprites, plus copies dimmed to the current brightness.

    Dimming an additive sprite means rebuilding it, so brightness is snapped to STEPS levels and
    the copies are only rebuilt when the level changes."""
    STEPS = 16

    def __init__(self, glows):
        self.base = glows
        self._level = None
        self._dimmed = {}

    def at(self, level):
        q = round(max(0.0, min(1.0, level)) * self.STEPS)
        if q != self._level:
            self._level = q
            k = round(255 * q / self.STEPS)
            self._dimmed = {}
            for name, glow in self.base.items():
                g = glow.copy()
                g.fill((k, k, k), special_flags=pygame.BLEND_RGB_MULT)
                self._dimmed[name] = g
        return self._dimmed
