"""The title screen over the live city: the paint picker and how to play."""
import pygame

from iso import ZOOM

from ..config import SCREEN_H, SCREEN_W

PREVIEW_SCALE = 3 / ZOOM    # the sprites already carry ZOOM pixels per world unit
SPACING = 140


PLAYER_COLORS = ((255, 80, 160), (80, 220, 255))


class MenuView:
    def __init__(self, text, player_stacks):
        self.text, self.stacks = text, player_stacks
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

    def draw(self, scr, t, paints, choice, started, device, player, players):
        """One player's title screen on `scr`. device: what steers them (None: nothing yet).
        player: their index; players: how many are playing."""
        text = lambda *a, **k: self.text.draw(*a, dst=scr, **k)  # noqa: E731
        scr.blit(self.shade, (0, 0))
        title = "DRIFT DREAMS"
        for k, col in enumerate(((255, 90, 170), (90, 220, 255))):
            text(title, "big", col, (SCREEN_W / 2 + (k * 2 - 1) * 3, 130), "center", shadow=False)
        text(title, "big", (255, 245, 255), (SCREEN_W / 2, 130), "center", shadow=False)
        text("an open-world drift through the city", "normal", (230, 220, 255), (SCREEN_W / 2, 200), "center")

        scr.blit(self.band, (0, 245))
        n = len(paints)
        for k, name in enumerate(paints):
            x = SCREEN_W / 2 + (k - (n - 1) / 2) * SPACING
            big, (ax, ay) = self._preview(name, t * 60 + k * 30)
            if k == choice:
                pygame.draw.rect(scr, (255, 214, 60), pygame.Rect(x - 62, 262, 124, 120), 3, 10)
            scr.blit(big, (x - ax, 336 - ay))
        text(paints[choice].upper(), "normal", (255, 214, 60), (SCREEN_W / 2, 400), "center")
        verb = "drive" if not started else "keep driving"
        pad = device is not None and device.startswith("Controller")
        quit_ = "leave" if player else "quit"
        if pad:
            line = f"LEFT/RIGHT paint   A/START {verb}   BACK {quit_}"
        elif device and "right half" in device:
            line = f"LEFT/RIGHT paint   ENTER {verb}   BACKSPACE {quit_}"
        elif device and "left half" in device:
            line = f"A/D paint   SPACE {verb}   ESC {quit_}"
        else:
            line = f"LEFT/RIGHT paint   ENTER {verb}   ESC {quit_}"
        text(line, "normal", (240, 240, 240), (SCREEN_W / 2, 470), "center")
        if device:
            text(device, "small", (170, 200, 255), (SCREEN_W / 2, 610), "center")
        if players > 1:
            text(f"PLAYER {player + 1}", "mid", PLAYER_COLORS[player], (24, 20), shadow=True)
            text("2 / F2: player 2 leaves", "small", (200, 200, 230), (SCREEN_W / 2, 650), "center")
        else:
            text("Second player: START on another pad, or press 2", "small", (200, 200, 230),
                 (SCREEN_W / 2, 650), "center")
        text("Hold handbrake while turning to drift. Drifts, near misses and smashes chain into combos.",
             "small", (220, 210, 240), (SCREEN_W / 2, 530), "center")
        text("Crashing or drifting off the tarmac loses the combo.",
             "small", (220, 210, 240), (SCREEN_W / 2, 556), "center")
