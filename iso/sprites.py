"""Atlas loading and 2.5D sprite stacks projected into the 2:1 isometric view."""
import json
import math
import os

import pygame


def load_atlas(folder, name):
    """Frames of a spritegen sheet by name, plus its animations."""
    with open(os.path.join(folder, name + ".atlas.json")) as fh:
        data = json.load(fh)
    sheet = pygame.image.load(os.path.join(folder, data["meta"]["image"])).convert_alpha()
    frames = {}
    for key, info in data["frames"].items():
        f = info["frame"]
        frames[key] = sheet.subsurface(pygame.Rect(f["x"], f["y"], f["w"], f["h"])).copy()
    return frames, data.get("animations", {})


def load_pivots(folder, name):
    """Each frame's pivot in pixels from its top-left corner, for frames that have one."""
    with open(os.path.join(folder, name + ".atlas.json")) as fh:
        data = json.load(fh)
    out = {}
    for key, info in data["frames"].items():
        if "pivot" in info:
            size = info["sourceSize"]
            out[key] = (round(info["pivot"]["x"] * size["w"]), round(info["pivot"]["y"] * size["h"]))
    return out


def stack_slices(frames, prefix):
    """Slices `prefix_0..N` of a sprite stack, bottom first."""
    out = []
    while f"{prefix}_{len(out)}" in frames:
        out.append(frames[f"{prefix}_{len(out)}"])
    return out


class IsoStack:
    """A sprite stack pre-rendered at `steps` headings.

    Slices are top-down pictures with the front at the top. For each heading every slice is
    rotated clockwise on the ground, mapped through the iso projection (x - y, (x + y) / 2)
    with nearest-neighbour sampling, and drawn `lift` pixels above the one below it.
    image(deg) returns (surface, anchor), anchor being where the ground centre lands.
    """

    def __init__(self, slices, steps=72, lift=1, shadow=True, angles=None, shadow_offset=(4, 2)):
        self.steps = steps
        self.lift = lift
        w, h = slices[0].get_size()
        self.size = (w, h)
        # every slice as one RGBA texel per list entry, plus a transparent one at the end that
        # output pixels outside the slice point at; identical slices share one entry
        clear = b"\0\0\0\0"
        self.slices, self.order, seen = [], [], {}
        for s in slices:
            raw = pygame.image.tobytes(s, "RGBA")
            if raw not in seen:
                seen[raw] = len(self.slices)
                self.slices.append([raw[i:i + 4] for i in range(0, len(raw), 4)] + [clear])
            self.order.append(seen[raw])
        biggest = max(self.slices, key=lambda px: sum(p[3] > 0 for p in px))
        dark = bytes((0, 0, 0, 70))
        self.shadow_px = [dark if p[3] else clear for p in biggest]
        self.shadow = shadow
        self.shadow_offset = shadow_offset
        self.images = {}
        for k in (angles if angles is not None else range(steps)):
            self.images[k] = self._render(k * 360 / steps)

    def _render(self, deg):
        w, h = self.size
        cx, cy = w / 2, h / 2
        r = math.hypot(w, h) / 2 + 1
        n = len(self.order)
        half = int(2 * r) + 1
        ground = int(r) + 1                     # rows below the ground centre
        ow, gh = 2 * half, 2 * ground
        so = self.shadow_offset
        oh = gh + math.ceil(self.lift * n) + so[1]
        ax, ay = half, oh - ground - so[1]
        a = math.radians(deg)
        ca, sa = math.cos(a), math.sin(a)
        # inverse map: every pixel of the ground footprint -> world offset -> slice texel index
        out_of_slice = w * h
        index = []
        for oy in range(-ground, ground):
            sy = oy + 0.5
            for ox in range(-half, half):
                sx = ox + 0.5
                wx, wy = sy + sx / 2, sy - sx / 2
                tx, ty = wx * ca + wy * sa + cx, -wx * sa + wy * ca + cy
                index.append(int(ty) * w + int(tx) if 0 <= tx < w and 0 <= ty < h else out_of_slice)

        def project(px):
            return pygame.image.frombytes(b"".join(map(px.__getitem__, index)), (ow, gh), "RGBA")

        surf = pygame.Surface((ow, oh), pygame.SRCALPHA)
        top = ay - ground
        if self.shadow:
            surf.blit(project(self.shadow_px), (so[0], top + so[1]))
        flat = [project(px) for px in self.slices]
        for i, k in enumerate(self.order):
            # a fractional lift repeats some slices to fill the gap up to the next one
            lo = int(i * self.lift)
            for lift in range(lo, max(lo + 1, int((i + 1) * self.lift))):
                surf.blit(flat[k], (0, top - lift))
        bbox = surf.get_bounding_rect()
        return _for_display(surf.subsurface(bbox).copy()), (ax - bbox.x, ay - bbox.y)

    def index(self, deg):
        return int(round(deg * self.steps / 360)) % self.steps

    def image(self, deg):
        return self.images[self.index(deg)]

    def recolored(self, mapping):
        """A copy with colours swapped, e.g. a car body repainted: [(old, new), ...]."""
        out = object.__new__(IsoStack)
        out.__dict__.update(self.__dict__)
        out.images = {}
        for k, (surf, anchor) in self.images.items():
            s = surf.copy()
            px = pygame.PixelArray(s)
            for old, new in mapping:
                px.replace(old, new)
            del px
            out.images[k] = (s, anchor)
        return out


def _for_display(surf):
    """The surface in the display's pixel format, which blits several times faster, once there
    is a display (the sprite tools use stacks without one)."""
    return surf.convert_alpha() if pygame.display.get_surface() is not None else surf


def blit_anchored(dst, img, pos):
    surf, (ax, ay) = img
    dst.blit(surf, (round(pos[0]) - ax, round(pos[1]) - ay))
