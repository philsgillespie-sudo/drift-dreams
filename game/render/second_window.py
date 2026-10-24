"""Player 2's window. pygame.display only opens one window, so this one is an SDL window of its own:
the view is drawn as usual (on the main window's surface, see Game.draw) and uploaded to this
window's texture once a frame."""
import ctypes
import os

import pygame
from pygame._sdl2.video import Renderer, Texture, Window


class _Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("w", ctypes.c_int), ("h", ctypes.c_int)]


def display_bounds():
    """[(x, y, w, h)] of each monitor on the desktop."""
    sizes = pygame.display.get_desktop_sizes()
    try:
        sdl = ctypes.CDLL(os.path.join(os.path.dirname(pygame.__file__), "SDL2.dll"))
        out = []
        for i in range(len(sizes)):
            r = _Rect()
            if sdl.SDL_GetDisplayBounds(i, ctypes.byref(r)) != 0:
                raise OSError
            out.append((r.x, r.y, r.w, r.h))
        return out
    except (OSError, AttributeError):
        # no SDL to ask: guess the monitors sit left to right
        out, x = [], 0
        for w, h in sizes:
            out.append((x, 0, w, h))
            x += w
        return out


class SecondWindow:
    def __init__(self, size, title):
        self.size = size
        self.window = Window(title, size, resizable=True)
        # only the main window waits for vsync: two waits a frame would halve the frame rate
        self.renderer = Renderer(self.window, vsync=False)
        self.renderer.logical_size = size                # scale to the window, like pygame.SCALED
        self.texture = Texture(self.renderer, size, streaming=True)
        self.texture.blend_mode = 0     # copy, don't blend: the screen's unused alpha byte is junk
        self._place()

    def _place(self):
        """Fill the second monitor; with only one, sit beside the main window, both half the screen."""
        monitors = display_bounds()
        if os.environ.get("SDL_VIDEO_DRIVER") == "dummy":
            return
        if len(monitors) > 1:
            x, y, w, h = monitors[1]
            self.window.position = (x + 40, y + 40)
            self.window.borderless = True
            self.window.position = (x, y)
            self.window.size = (w, h)
            return
        x, y, w, h = monitors[0]
        half = w // 2
        size = (half, half * self.size[1] // self.size[0])
        top = y + max(0, (h - size[1]) // 2)
        main = Window.from_display_module()
        main.size, main.position = size, (x, top)
        self.window.size, self.window.position = size, (x + half, top)

    @property
    def id(self):
        return self.window.id

    def present(self, surface):
        """Show `surface` (copied now, so it can be drawn over straight after)."""
        self.texture.update(surface)
        self.renderer.clear()
        self.renderer.blit(self.texture)
        self.renderer.present()

    def close(self):
        self.window.destroy()
