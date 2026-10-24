"""Text drawing with the rendered lines cached: most HUD text is the same from frame to frame."""
from collections import OrderedDict

import pygame

MONO = "consolas,menlo,monospace"
SIZES = {"small": 16, "normal": 22, "mid": 40, "big": 92}
CACHE = 256


class Text:
    def __init__(self, screen):
        self.screen = screen
        self.fonts = {name: pygame.font.SysFont(MONO, size, bold=True) for name, size in SIZES.items()}
        self._cache = OrderedDict()

    def render(self, s, size, color, shadow=True):
        """(image, shadow image or None) for a line of text."""
        key = (s, size, color, shadow)
        hit = self._cache.get(key)
        if hit is not None:
            self._cache.move_to_end(key)
            return hit
        font = self.fonts[size]
        hit = (font.render(s, True, color), font.render(s, True, (0, 0, 0)) if shadow else None)
        self._cache[key] = hit
        if len(self._cache) > CACHE:
            self._cache.popitem(last=False)
        return hit

    def draw(self, s, size, color, pos, anchor="topleft", shadow=True):
        img, back = self.render(s, size, color, shadow)
        rect = img.get_rect(**{anchor: pos})
        if back is not None:
            self.screen.blit(back, rect.move(2, 2))
        self.screen.blit(img, rect)
        return rect
