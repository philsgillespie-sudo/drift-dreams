"""The title screen over the live city: the paint picker and how to play."""
import pygame

from iso import ZOOM

from ..config import SCREEN_H, SCREEN_W

PREVIEW_SCALE = 3 / ZOOM    # the sprites already carry ZOOM pixels per world unit
SPACING = 140


class MenuView:
    def __init__(self, screen, text, player_stacks):
        self.screen, self.text, self.stacks = screen, text, player_stacks
        self.shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.shade.fill((20, 0, 40, 120))
        self.band = pygame.Surface((SCREEN_W, 170), pygame.SRCALPHA)
        self.band.fill((20, 0, 40, 140))
        self._previews = {}   # (paint, heading step) -> (scaled image, anchor)

    def _preview(self, name, deg):
        stack = self.stacks[name]
        key = (name, stack.index(deg))
        img = self._previews.get(key)
        if img is None:
            surf, (ax, ay) = stack.image(deg)
            size = (round(surf.get_width() * PREVIEW_SCALE), round(surf.get_height() * PREVIEW_SCALE))
            img = self._previews[key] = (pygame.transform.smoothscale(surf, size),
                                         (ax * PREVIEW_SCALE, ay * PREVIEW_SCALE))
        return img

    def draw(self, t, paints, choice, started, gamepad_name):
        scr, text = self.screen, self.text
        scr.blit(self.shade, (0, 0))
        title = "DRIFT DREAMS"
        for k, col in enumerate(((255, 90, 170), (90, 220, 255))):
            text.draw(title, "big", col, (SCREEN_W / 2 + (k * 2 - 1) * 3, 130), "center", shadow=False)
        text.draw(title, "big", (255, 245, 255), (SCREEN_W / 2, 130), "center", shadow=False)
        text.draw("an open-world drift through the city", "normal", (230, 220, 255), (SCREEN_W / 2, 200), "center")

        scr.blit(self.band, (0, 245))
        n = len(paints)
        for k, name in enumerate(paints):
            x = SCREEN_W / 2 + (k - (n - 1) / 2) * SPACING
            big, (ax, ay) = self._preview(name, t * 60 + k * 30)
            if k == choice:
                pygame.draw.rect(scr, (255, 214, 60), pygame.Rect(x - 62, 262, 124, 120), 3, 10)
            scr.blit(big, (x - ax, 336 - ay))
        text.draw(paints[choice].upper(), "normal", (255, 214, 60), (SCREEN_W / 2, 400), "center")
        verb = "drive" if not started else "keep driving"
        if gamepad_name:
            text.draw(f"LEFT/RIGHT paint   A/START {verb}   BACK quit", "normal", (240, 240, 240),
                      (SCREEN_W / 2, 470), "center")
            text.draw(f"Controller: {gamepad_name}", "small", (170, 200, 255), (SCREEN_W / 2, 610), "center")
        else:
            text.draw(f"LEFT/RIGHT paint   ENTER {verb}   ESC quit", "normal", (240, 240, 240),
                      (SCREEN_W / 2, 470), "center")
        text.draw("Hold handbrake while turning to drift. Drifts, near misses and smashes chain into combos.",
                  "small", (220, 210, 240), (SCREEN_W / 2, 530), "center")
        text.draw("Crashing or drifting off the tarmac loses the combo.",
                  "small", (220, 210, 240), (SCREEN_W / 2, 556), "center")
