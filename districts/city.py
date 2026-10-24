"""The city district: a seeded street grid of blocks with its buildings and scenery.

It sits at the world origin, so its local tiles are world tiles. World units: one tile is T x T on
the ground and draws as a TILE_W x TILE_H diamond. Roads run along the world x and y axes; the iso
view turns them into the two diagonals on screen.
"""
import math
import random

import pygame
from pygame.math import Vector2 as V

from iso import ZOOM

from .base import TILE_H, TILE_W, T, District

BLOCKS = 9          # city blocks along each axis
ROAD = 3            # road width in tiles
INNER = 8           # block interior in tiles (a sidewalk ring goes around it)
PITCH = ROAD + 1 + INNER + 1
EDGE = 6            # beach and sea around the land
SIZE = EDGE * 2 + ROAD + BLOCKS * PITCH
FLOOR_H = 24 * ZOOM  # one building floor in pixels


def road_start(k):
    return EDGE + k * PITCH


def road_band(t):
    """Index of the road band containing tile row/column t, or None."""
    off = t - EDGE
    if off < 0:
        return None
    k, r = divmod(off, PITCH)
    return k if r < ROAD and k <= BLOCKS else None


def block_of(t):
    """(block index, local tile 0..9) for a tile inside a block band: 0 and 9 are sidewalk."""
    k, r = divmod(t - EDGE, PITCH)
    return k, r - ROAD


def node_pos(a, b):
    """Centre of the intersection of road column a and road row b."""
    return V((road_start(a) + 1.5) * T, (road_start(b) + 1.5) * T)


def node_key(a, b):
    """The road graph's key for the junction of road column a and road row b."""
    return ("city", a, b)


class Lot:
    def __init__(self, style, floors, shop, mid, tiles):
        self.style, self.floors, self.shop, self.mid = style, floors, shop, mid
        self.tiles = tiles


class City(District):
    def __init__(self, tiles, buildings, seed=7):
        super().__init__(0, 0, SIZE, SIZE, tiles)
        self.rng = random.Random(seed)
        self.bframes = buildings
        self.block_type = {}
        self._bcache = {}
        self._layout()

    # -- generation --------------------------------------------------------
    def _layout(self):
        rng = self.rng
        n = SIZE
        for j in range(EDGE - 2, n - EDGE + 2):
            for i in range(EDGE - 2, n - EDGE + 2):
                self.ground[j][i] = "sand"
                self.solid[j][i] = 0

        blocks = [(bx, by) for by in range(BLOCKS) for bx in range(BLOCKS)]
        mid = BLOCKS // 2
        types = {b: "city" for b in blocks}
        types[(mid, mid)] = "plaza"
        pool = [b for b in blocks if b != (mid, mid)]
        rng.shuffle(pool)
        for b in pool[:7]:
            types[b] = "park"
        for b in pool[7:12]:
            types[b] = "parking"
        types[pool[12]] = "plaza"
        self.block_type = types

        for j in range(EDGE, n - EDGE):
            for i in range(EDGE, n - EDGE):
                self._road_tile(i, j)
        for (bx, by), kind in types.items():
            x0 = road_start(bx) + ROAD
            y0 = road_start(by) + ROAD
            self._sidewalk_ring(x0, y0, kind)
            getattr(self, "_" + kind)(x0 + 1, y0 + 1, bx, by)

        c = road_start(mid) + ROAD + 1 + INNER / 2
        self.start = V(c * T, c * T)

    def _road_tile(self, i, j):
        rx, ry = road_band(i), road_band(j)
        if rx is None and ry is None:
            return
        self.solid[j][i] = 0
        rng = self.rng
        if rx is not None and ry is not None:
            name = "manhole" if rng.random() < 0.05 else "asphalt"
        else:
            along, across, band = ("x", j, ry) if ry is not None else ("y", i, rx)
            local = block_of(i if along == "x" else j)[1]
            if local in (0, INNER + 1):
                name = "cross_" + along
            elif across - road_start(band) == 1:
                name = "lane_" + along
            else:
                r = rng.random()
                name = "asphalt_crack" if r < 0.06 else "manhole" if r < 0.09 else "asphalt"
        self.ground[j][i] = name

    def _sidewalk_ring(self, x0, y0, kind):
        last = INNER + 1
        rng = self.rng
        for ly in range(last + 1):
            for lx in range(last + 1):
                if lx not in (0, last) and ly not in (0, last):
                    continue
                i, j = x0 + lx, y0 + ly
                self.ground[j][i] = "sidewalk"
                self.solid[j][i] = 0
                curbs = []
                for side, (di, dj) in (("n", (0, -1)), ("s", (0, 1)), ("w", (-1, 0)), ("e", (1, 0))):
                    if road_band(i + di) is not None and di or road_band(j + dj) is not None and dj:
                        curbs.append("curb_" + side)
                if curbs:
                    self.overlays[(i, j)] = curbs
                centre = V((i + 0.5) * T, (j + 0.5) * T)
                # lamps along the kerb, arm out over the road
                if (lx + ly) % 4 == 2 and curbs and len(curbs) == 1:
                    side = curbs[0][-1]
                    out = {"n": V(0, -1), "s": V(0, 1), "w": V(-1, 0), "e": V(1, 0)}[side]
                    ang = {"e": 0, "s": 90, "w": 180, "n": 270}[side]
                    self._add_static("lamp", centre + out * 11, ang)
                elif kind == "city" and (lx + ly) % 4 == 0 and rng.random() < 0.6 and curbs:
                    self._add_static("tree", centre + V(rng.uniform(-3, 3), rng.uniform(-3, 3)),
                                     rng.choice((0, 90, 180, 270)))
                elif rng.random() < 0.06:
                    self.prop_spots.append(("hydrant" if rng.random() < 0.5 else "bin",
                                            centre + V(rng.uniform(-6, 6), rng.uniform(-6, 6))))

    def _set_area(self, x0, y0, w, h, name):
        for j in range(y0, y0 + h):
            for i in range(x0, x0 + w):
                self.ground[j][i] = name
                self.solid[j][i] = 0

    def _city(self, x0, y0, bx, by):
        rng = self.rng
        self._set_area(x0, y0, INNER, INNER, "plaza")
        c = (BLOCKS - 1) / 2
        df = math.hypot(bx - c, by - c) / (c * 1.414)
        rects = []
        if rng.random() < 0.35:
            # a two-tile alley through the block
            along_x = rng.random() < 0.5
            for a in (0, 5):
                for b in (0, 4):
                    rects.append((b, a, 4, 3) if along_x else (a, b, 3, 4))
            ax, ay, aw, ah = (0, 3, INNER, 2) if along_x else (3, 0, 2, INNER)
            for j in range(ay, ay + ah):
                for i in range(ax, ax + aw):
                    self.ground[y0 + j][x0 + i] = "asphalt_crack" if rng.random() < 0.15 else "asphalt"
        else:
            for a in (0, 4):
                for b in (0, 4):
                    r = rng.random()
                    if r < 0.25:
                        rects += [(a, b, 4, 2), (a, b + 2, 4, 2)]
                    elif r < 0.5:
                        rects += [(a, b, 2, 4), (a + 2, b, 2, 4)]
                    else:
                        rects.append((a, b, 4, 4))
        for (lx, ly, w, h) in rects:
            top = max(1, round(9 - 7.5 * df))
            floors = rng.randint(max(1, top - 3), top)
            if df < 0.45 and rng.random() < 0.6:
                style = "glass"
                floors += 1
            else:
                style = rng.choice(("brick", "brick", "concrete", "cream", "pastel"))
            shop = style != "glass" and rng.random() < 0.55
            tiles = [(x0 + lx + i, y0 + ly + j) for j in range(h) for i in range(w)]
            lot = Lot(style, floors, shop, rng.choice(("mid", "mid_b")), set(tiles))
            clutter_tile = rng.choice(tiles)
            clutter = rng.choice(("roof_ac", "roof_tank", "roof_ac", None))
            for (i, j) in tiles:
                rims = tuple(s for s, (di, dj) in (("n", (0, -1)), ("e", (1, 0)), ("s", (0, 1)), ("w", (-1, 0)))
                             if (i + di, j + dj) not in lot.tiles)
                self.buildings[(i, j)] = (lot, rims, clutter if (i, j) == clutter_tile else None)
                self.solid[j][i] = 1

    def _park(self, x0, y0, bx, by):
        rng = self.rng
        for j in range(INNER):
            for i in range(INNER):
                path = i in (3, 4) or j in (3, 4)
                name = "dirt" if path else ("grass_flowers" if rng.random() < 0.15 else "grass")
                self.ground[y0 + j][x0 + i] = name
                self.solid[y0 + j][x0 + i] = 0
                if not path and rng.random() < 0.45:
                    centre = V((x0 + i + 0.5) * T, (y0 + j + 0.5) * T)
                    kind = rng.choice(("tree", "tree", "pine", "bush"))
                    self._add_static(kind, centre + V(rng.uniform(-6, 6), rng.uniform(-6, 6)),
                                     rng.choice((0, 90, 180, 270)))

    def _plaza(self, x0, y0, bx, by):
        self._set_area(x0, y0, INNER, INNER, "plaza")
        c = V((x0 + INNER / 2) * T, (y0 + INNER / 2) * T)
        for k in range(12):
            a = k / 12 * math.tau
            self.prop_spots.append(("cone", c + V(math.cos(a), math.sin(a)) * 72))
        for k in (-1, 1):
            self.prop_spots.append(("cone", c + V(k * 150, -150)))
            self.prop_spots.append(("cone", c + V(k * 150, 150)))
        for i, j in ((0, 0), (INNER - 1, 0), (0, INNER - 1), (INNER - 1, INNER - 1)):
            self._add_static("tree", V((x0 + i + 0.5) * T, (y0 + j + 0.5) * T), 0)

    def _parking(self, x0, y0, bx, by):
        rng = self.rng
        for j in range(INNER):
            for i in range(INNER):
                stall = j in (0, 1, 6, 7)
                self.ground[y0 + j][x0 + i] = "park_line_x" if stall and j in (0, 7) else "asphalt"
                self.solid[y0 + j][x0 + i] = 0
                if j in (0, 7) and rng.random() < 0.45:
                    pos = V((x0 + i + 0.5) * T, (y0 + j + 0.55) * T)
                    self.parked.append((pos, 0 if j == 0 else math.pi))
        for k in range(5):
            self.prop_spots.append(("cone", V((x0 + 1.5 + k * 1.25) * T, (y0 + 4) * T)))

    # -- roads -----------------------------------------------------------------
    def add_roads(self, graph):
        """A junction where every road column crosses every road row, joined to its neighbours."""
        for b in range(BLOCKS + 1):
            for a in range(BLOCKS + 1):
                graph.add_node(node_key(a, b), node_pos(a, b))
        for b in range(BLOCKS + 1):
            for a in range(BLOCKS + 1):
                if a < BLOCKS:
                    graph.connect(node_key(a, b), node_key(a + 1, b))
                if b < BLOCKS:
                    graph.connect(node_key(a, b), node_key(a, b + 1))

    # -- drawing -------------------------------------------------------------
    def building_image(self, i, j):
        """The whole stack for one building tile and the row of its ground diamond's top corner.
        Tiles that look alike share one image."""
        lot, rims, clutter = self.buildings[(i, j)]
        ground = "shop" if lot.shop else "base"
        key = (lot.style, ground, lot.mid, lot.floors, rims, clutter)
        img = self._bcache.get(key)
        if img is None:
            f = self.bframes
            gy = (lot.floors + 1) * FLOOR_H
            surf = pygame.Surface((TILE_W, gy + TILE_H), pygame.SRCALPHA)
            for k in range(lot.floors):
                kind = ground if k == 0 else lot.mid
                surf.blit(f[f"{lot.style}_{kind}"], (0, gy - FLOOR_H - k * FLOOR_H))
            surf.blit(f["roof"], (0, 0))
            for side in rims:
                surf.blit(f["rim_" + side], (0, 0))
            if clutter:
                surf.blit(f[clutter], (0, 0))
            img = self._bcache[key] = (surf.convert_alpha(), gy)
        return img
