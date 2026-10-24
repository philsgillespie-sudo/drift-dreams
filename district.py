"""A district: one rectangular piece of the world with its own tile grid, baked ground and objects.

Districts sit side by side in one world tile space (see world.World). A district at tile offset
(ox, oy) keeps its grids in local coordinates, [j][i] with 0 <= i < w; everything handed out
(buildings, scenery, decorations, positions) is in world coordinates.
"""
import math

import pygame
from pygame.math import Vector2 as V

from iso import ZOOM

T = 32
CHUNK = 8           # ground is baked in CHUNK x CHUNK tile pieces
TILE_W, TILE_H = 64 * ZOOM, 32 * ZOOM   # one ground tile on screen
COLORKEY = (255, 0, 255)


class District:
    def __init__(self, ox, oy, w, h, tiles):
        self.ox, self.oy, self.w, self.h = ox, oy, w, h
        self.tile_img = tiles
        self.ground = [["water"] * w for _ in range(h)]     # [j][i], local
        self.solid = [[2] * w for _ in range(h)]            # 0 open, 1 building, 2 sea
        self.overlays = {}                                   # local (i, j) -> overlay tiles
        self.buildings = {}                                  # world (i, j) -> (lot, rims, clutter)
        self.statics = {}                                    # world (i, j) -> [(kind, pos, angle)]
        self.decos = []                                      # (name, world i, world j, depth)
        self.prop_spots = []                                 # (kind, pos)
        self.parked = []                                     # (pos, heading)
        self._chunk_cache = {}

    def finish(self):
        """Call once the layout is final (neighbours may still lay tiles into it until then)."""
        self.chunks_w = math.ceil(self.w / CHUNK)
        self.chunks_h = math.ceil(self.h / CHUNK)
        self._index_chunks()

    # -- queries, world tile coordinates -----------------------------------------
    def contains(self, i, j):
        return 0 <= i - self.ox < self.w and 0 <= j - self.oy < self.h

    def ground_w(self, i, j):
        return self.ground[j - self.oy][i - self.ox]

    def solid_w(self, i, j):
        return self.solid[j - self.oy][i - self.ox]

    def _add_static(self, kind, pos, angle=0):
        key = (int(pos.x // T), int(pos.y // T))
        self.statics.setdefault(key, []).append((kind, V(pos), angle))

    def nearest_road(self, p):
        """Centre of the nearest lane, and the heading along it, for putting a car back."""
        raise NotImplementedError

    def draw_cables(self, dst, cam, side):
        """Overhead lines drawn behind ("back") or in front of ("front") everything standing."""

    # -- drawing -------------------------------------------------------------
    def _index_chunks(self):
        """Buildings and scenery bucketed by ground chunk, for culling."""
        self.chunk_objs = {}
        for (i, j) in self.buildings:
            self.chunk_objs.setdefault(((i - self.ox) // CHUNK, (j - self.oy) // CHUNK), []).append(("building", i, j))
        for (i, j), items in self.statics.items():
            for kind, p, ang in items:
                self.chunk_objs.setdefault(((i - self.ox) // CHUNK, (j - self.oy) // CHUNK), []).append(
                    ("static", kind, p, ang))

    def chunk_rect(self, ci, cj):
        i0, j0 = self.ox + ci * CHUNK, self.oy + cj * CHUNK
        hw, hh = TILE_W // 2, TILE_H // 2
        return pygame.Rect((i0 - j0) * hw - CHUNK * hw, (i0 + j0) * hh, CHUNK * TILE_W, CHUNK * TILE_H)

    def _bake_chunk(self, ci, cj):
        rect = self.chunk_rect(ci, cj)
        surf = pygame.Surface(rect.size).convert()
        surf.fill(COLORKEY)
        surf.set_colorkey(COLORKEY, pygame.RLEACCEL)
        for j in range(cj * CHUNK, min(self.h, (cj + 1) * CHUNK)):
            for i in range(ci * CHUNK, min(self.w, (ci + 1) * CHUNK)):
                wi, wj = i + self.ox, j + self.oy
                x, y = (wi - wj) * (TILE_W // 2) - TILE_W // 2 - rect.x, (wi + wj) * (TILE_H // 2) - rect.y
                surf.blit(self.tile_img[self.ground[j][i]], (x, y))
                for ov in self.overlays.get((i, j), ()):
                    surf.blit(self.tile_img[ov], (x, y))
        return surf

    def visible_chunks(self, view, extra_top=0):
        out = []
        for cj in range(self.chunks_h):
            for ci in range(self.chunks_w):
                r = self.chunk_rect(ci, cj)
                if extra_top:
                    r.top -= extra_top
                    r.height += extra_top
                if r.colliderect(view):
                    out.append((ci, cj))
        return out

    def draw_ground(self, dst, cam):
        view = cam.view
        for ci, cj in self.visible_chunks(view):
            surf = self._chunk_cache.get((ci, cj))
            if surf is None:
                if len(self._chunk_cache) > 36:
                    self._chunk_cache.pop(next(iter(self._chunk_cache)))
                surf = self._chunk_cache[(ci, cj)] = self._bake_chunk(ci, cj)
            r = self.chunk_rect(ci, cj)
            dst.blit(surf, (r.x - cam.ox, r.y - cam.oy))
