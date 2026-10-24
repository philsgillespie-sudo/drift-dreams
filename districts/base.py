"""A district: one rectangular piece of the world with its own tile grid, baked ground and objects.

Districts sit side by side in one world tile space (see world.World). A district at tile offset
(ox, oy) keeps its grids in local coordinates, [j][i] with 0 <= i < w; everything handed out
(buildings, scenery, decorations, positions) is in world coordinates.

To add a district: subclass District, lay out ground/solid/buildings/statics in __init__, add its
roads in add_roads(), and register a builder in districts.LAYOUT.
"""
import math
from collections import OrderedDict, deque

import pygame
from pygame.math import Vector2 as V

from iso import ZOOM, iso

T = 32
CHUNK = 8           # ground is baked in CHUNK x CHUNK tile pieces
TILE_W, TILE_H = 64 * ZOOM, 32 * ZOOM   # one ground tile on screen
COLORKEY = (255, 0, 255)
CHUNK_CACHE = 40    # baked ground chunks kept per district, least recently drawn dropped first
PREFETCH = (CHUNK * TILE_W // 2, CHUNK * TILE_H // 2)   # bake ahead within this much past the view
MARKS_PER_CHUNK = 600   # skid marks remembered per chunk (for re-baking)
MARK_WIDTH = 2 * ZOOM - 1
# Fresh marks are drawn straight to the screen and painted into their (RLE-compressed, so costly to
# change) chunk in batches: once this many have piled up, or they've waited this many frames.
MARK_BATCH, MARK_WAIT = 48, 45
BLOCK_CACHE = 160       # building block images kept per district, least recently drawn dropped first
BLOCK_PREFETCH = 2      # block images made ahead of the view per idle frame


def tile_rect(i, j, gy):
    """Un-scrolled screen rect of a building tile's stack whose ground corner is gy rows down."""
    p = iso((i * T, j * T))
    return pygame.Rect(p.x - TILE_W // 2, p.y - gy, TILE_W, gy + TILE_H)


class BuildingBlock:
    """A square of one building's tiles, drawn as one image instead of a column per tile (far
    less overdraw). Squares, because a square footprint sorts against everything around it by one
    depth, x0 + y1 == x1 + y0, exactly as a single tile does; a longer footprint can't."""
    __slots__ = ("owner", "lot", "tiles", "depth", "rect")

    def __init__(self, owner, lot, i0, j0, n):
        self.owner, self.lot = owner, lot
        self.tiles = sorted(((i, j) for j in range(j0, j0 + n) for i in range(i0, i0 + n)),
                            key=lambda t: t[0] + t[1])     # back to front
        self.depth = (i0 + j0 + n) * T
        rects = [tile_rect(i, j, owner.building_image(i, j)[1]) for i, j in self.tiles]
        self.rect = rects[0].unionall(rects[1:])           # un-scrolled

    def image(self):
        return self.owner.block_image(self)


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
        self._chunk_cache = OrderedDict()
        self._marks = {}                                     # chunk -> deque of (a, b, colour)
        self._fresh_marks = {}                               # baked chunk -> [first frame, marks not on it yet]
        self._frame = 0
        self._block_images = OrderedDict()

    def finish(self):
        """Call once the layout is final (neighbours may still lay tiles into it until then)."""
        self.chunks_w = math.ceil(self.w / CHUNK)
        self.chunks_h = math.ceil(self.h / CHUNK)
        self._chunk_keys = [(ci, cj) for cj in range(self.chunks_h) for ci in range(self.chunks_w)]
        self._chunk_rects = [self.chunk_rect(ci, cj) for ci, cj in self._chunk_keys]
        self._tall_rects = {}
        self.blocks = self._split_buildings()
        self._block_rects = [b.rect for b in self.blocks]
        self._index_chunks()

    # -- hooks for subclasses ------------------------------------------------------
    def building_image(self, i, j):
        """(image, gy) for the building tile at world (i, j): the whole stack, and the row of its
        ground diamond's top corner. Districts with buildings override this."""
        raise NotImplementedError

    def add_roads(self, graph):
        """Add this district's junctions and roads to the world's roads.RoadGraph."""

    def draw_cables(self, dst, cam, side):
        """Overhead lines drawn behind ("back") or in front of ("front") everything standing."""

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

    # -- buildings ---------------------------------------------------------------
    def _split_buildings(self):
        """Every building's footprint (a rectangle of tiles) cut into squares, largest first."""
        lots = {}
        for (i, j), (lot, _, _) in self.buildings.items():
            lots.setdefault(id(lot), (lot, []))[1].append((i, j))
        blocks = []
        for lot, tiles in lots.values():
            i0, i1 = min(t[0] for t in tiles), max(t[0] for t in tiles) + 1
            j0, j1 = min(t[1] for t in tiles), max(t[1] for t in tiles) + 1
            while i0 < i1 and j0 < j1:
                n = min(i1 - i0, j1 - j0)
                blocks.append(BuildingBlock(self, lot, i0, j0, n))
                if i1 - i0 > n:
                    i0 += n
                else:
                    j0 += n
        return blocks

    def visible_blocks(self, view):
        blocks = self.blocks
        return [blocks[k] for k in view.collidelistall(self._block_rects)]

    def block_image(self, block):
        """The block's tile stacks drawn together, made on first use and cached."""
        cache = self._block_images
        img = cache.get(block)
        if img is not None:
            cache.move_to_end(block)
            return img
        r = block.rect
        surf = pygame.Surface(r.size, pygame.SRCALPHA)
        for i, j in block.tiles:
            tile, gy = self.building_image(i, j)
            t = tile_rect(i, j, gy)
            surf.blit(tile, (t.x - r.x, t.y - r.y))
        img = cache[block] = surf.convert_alpha()
        while len(cache) > BLOCK_CACHE:
            cache.popitem(last=False)
        return img

    def _prefetch_blocks(self, view):
        """Make a few block images just outside the view, so they're ready when they come in."""
        budget = BLOCK_PREFETCH
        for block in self.visible_blocks(view.inflate(*PREFETCH)):
            if block not in self._block_images:
                self.block_image(block)
                budget -= 1
                if not budget:
                    return True
        return budget < BLOCK_PREFETCH

    # -- chunks ----------------------------------------------------------------
    def _index_chunks(self):
        """Scenery bucketed by ground chunk, for culling."""
        self.chunk_objs = {}
        for (i, j), items in self.statics.items():
            for kind, p, ang in items:
                self.chunk_objs.setdefault(self._chunk_of(i, j), []).append(("static", kind, p, ang))

    def _chunk_of(self, i, j):
        return (i - self.ox) // CHUNK, (j - self.oy) // CHUNK

    def chunk_rect(self, ci, cj):
        i0, j0 = self.ox + ci * CHUNK, self.oy + cj * CHUNK
        hw, hh = TILE_W // 2, TILE_H // 2
        return pygame.Rect((i0 - j0) * hw - CHUNK * hw, (i0 + j0) * hh, CHUNK * TILE_W, CHUNK * TILE_H)

    def visible_chunks(self, view, extra_top=0):
        """Chunks whose ground (raised by extra_top, for things standing on it) meets `view`."""
        rects = self._chunk_rects
        if extra_top:
            rects = self._tall_rects.get(extra_top)
            if rects is None:
                rects = self._tall_rects[extra_top] = [
                    pygame.Rect(r.x, r.y - extra_top, r.w, r.h + extra_top) for r in self._chunk_rects]
        keys = self._chunk_keys
        return [keys[k] for k in view.collidelistall(rects)]

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
        self._paint_marks(surf, rect, self._marks.get((ci, cj), ()))
        self._fresh_marks.pop((ci, cj), None)
        return surf

    def _chunk_surface(self, key):
        cache = self._chunk_cache
        surf = cache.get(key)
        if surf is None:
            while len(cache) >= CHUNK_CACHE:
                gone, _ = cache.popitem(last=False)
                self._fresh_marks.pop(gone, None)    # painted in again if it's ever re-baked
            surf = cache[key] = self._bake_chunk(*key)
        else:
            cache.move_to_end(key)
        return surf

    def draw_ground(self, dst, cam):
        self._frame += 1
        view = cam.view
        baked_before = len(self._chunk_cache)
        rects, cw = self._chunk_rects, self.chunks_w
        for key in self.visible_chunks(view):
            surf = self._chunk_surface(key)
            r = rects[key[1] * cw + key[0]]
            dst.blit(surf, (r.x - cam.ox, r.y - cam.oy))
        # at most one more slow job a frame, and only on a frame that hasn't had one
        if len(self._chunk_cache) == baked_before and not self._settle_marks() and not self._prefetch(view):
            self._prefetch_blocks(view)

    def draw_fresh_marks(self, dst, cam):
        """Marks not yet painted into their chunk, drawn over the ground."""
        ox, oy = cam.ox, cam.oy
        for _, marks in self._fresh_marks.values():
            for a, b, color in marks:
                pa, pb = iso(a), iso(b)
                pygame.draw.line(dst, color, (pa.x - ox, pa.y - oy), (pb.x - ox, pb.y - oy), MARK_WIDTH)

    def _prefetch(self, view):
        """Bake one chunk just outside the view, so driving into it doesn't stall a frame.
        Returns whether it did."""
        for key in self.visible_chunks(view.inflate(*PREFETCH)):
            if key not in self._chunk_cache:
                self._chunk_surface(key)
                return True
        return False

    # -- skid marks ------------------------------------------------------------
    def add_mark(self, a, b, color):
        """A skid mark from world point a to b, painted into the ground under it."""
        mark = (a, b, color)
        for key in {self._chunk_of(int(a[0] // T), int(a[1] // T)), self._chunk_of(int(b[0] // T), int(b[1] // T))}:
            if not (0 <= key[0] < self.chunks_w and 0 <= key[1] < self.chunks_h):
                continue
            marks = self._marks.get(key)
            if marks is None:
                marks = self._marks[key] = deque(maxlen=MARKS_PER_CHUNK)
            marks.append(mark)
            if key in self._chunk_cache:
                self._fresh_marks.setdefault(key, [self._frame, []])[1].append(mark)

    def _settle_marks(self):
        """Paint one chunk's fresh marks into it, if any are due. Returns whether it did."""
        due = None
        for key, (since, marks) in self._fresh_marks.items():
            if len(marks) >= MARK_BATCH or self._frame - since >= MARK_WAIT:
                due = key
                break
        if due is None:
            return False
        _, marks = self._fresh_marks.pop(due)
        self._paint_marks(self._chunk_cache[due], self._chunk_rects[due[1] * self.chunks_w + due[0]], marks)
        return True

    @staticmethod
    def _paint_marks(surf, rect, marks):
        if not marks:
            return
        surf.lock()
        for a, b, color in marks:
            pa, pb = iso(a), iso(b)
            pygame.draw.line(surf, color, (pa.x - rect.x, pa.y - rect.y), (pb.x - rect.x, pb.y - rect.y), MARK_WIDTH)
        surf.unlock()
