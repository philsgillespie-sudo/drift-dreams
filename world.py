"""The world: the districts side by side in one tile space, and everything the game asks of the map.

Outside every district is open sea. The districts come from districts.LAYOUT; the world flattens
their tile grids into one lookup and joins their roads into one roads.RoadGraph.
"""
import math

import pygame
from pygame.math import Vector2 as V

from districts import LAYOUT, T
from iso import iso
from roads import RoadGraph

SURFACE = {"grass": "grass", "grass_flowers": "grass", "dirt": "gravel", "sand": "gravel"}
STATIC_RADIUS = {"tree": 6, "pine": 5, "bush": 7, "lamp": 3}
SIDEWALKS = frozenset(("sidewalk", "bridge_walk"))
MINIMAP_COLORS = {"water": (40, 90, 150), "sand": (220, 205, 150), "grass": (80, 150, 60),
                  "grass_flowers": (80, 150, 60), "dirt": (170, 140, 95), "plaza": (200, 185, 150),
                  "sidewalk": (170, 165, 155), "bridge_walk": (170, 165, 155), "park_line_x": (90, 90, 100)}


class World:
    def __init__(self, art, decos, layout=LAYOUT):
        """art: districts.DistrictArt; decos: name -> (surface, pivot) for the decorations districts
        place; layout: name -> builder(art, built_so_far) -> District, built in order."""
        built = {}
        for name, build in layout.items():
            built[name] = build(art, built)
        self.by_name = built
        self.districts = list(built.values())
        for d in self.districts:
            d.finish()
        self.roads = RoadGraph()
        for d in self.districts:
            d.add_roads(self.roads)

        self.statics, self.buildings = {}, {}
        self.prop_spots, self.parked = [], []
        self.decos = []      # (name, depth, screen rect before scrolling)
        for d in self.districts:
            self.statics.update(d.statics)
            self.buildings.update(d.buildings)
            self.prop_spots += d.prop_spots
            self.parked += d.parked
            for name, i, j, depth in d.decos:
                surf, (ax, ay) = decos[name]
                p = iso((i * T, j * T))
                self.decos.append((name, depth, pygame.Rect(p.x - ax, p.y - ay, *surf.get_size())))
        self._deco_rects = [rect for _, _, rect in self.decos]
        self.start = next(d.start for d in self.districts if hasattr(d, "start"))
        self._build_grid()
        self._build_minimap()

    def _build_grid(self):
        """One flat tile lookup over every district, so queries don't search for the district."""
        ds = self.districts
        self.i0, self.j0 = min(d.ox for d in ds), min(d.oy for d in ds)
        self.iw = max(d.ox + d.w for d in ds) - self.i0
        self.jh = max(d.oy + d.h for d in ds) - self.j0
        n = self.iw * self.jh
        self._solid, self._ground, self._owner = [2] * n, ["water"] * n, [None] * n
        for d in ds:
            for lj in range(d.h):
                row = (d.oy + lj - self.j0) * self.iw + d.ox - self.i0
                self._solid[row:row + d.w] = d.solid[lj]
                self._ground[row:row + d.w] = d.ground[lj]
                self._owner[row:row + d.w] = [d] * d.w

    def _index(self, i, j):
        i -= self.i0
        j -= self.j0
        return j * self.iw + i if 0 <= i < self.iw and 0 <= j < self.jh else -1

    # -- queries ---------------------------------------------------------------
    def district_at(self, i, j):
        k = self._index(i, j)
        return self._owner[k] if k >= 0 else None

    def solid_at(self, i, j):
        k = self._index(i, j)
        return self._solid[k] if k >= 0 else 2

    def ground_at(self, p):
        k = self._index(int(p[0] // T), int(p[1] // T))
        return self._ground[k] if k >= 0 else "water"

    def surface_at(self, p):
        return SURFACE.get(self.ground_at(p), "road")

    def on_sidewalk(self, p):
        return self.ground_at(p) in SIDEWALKS

    def collide(self, pos, r):
        """Push a circle out of buildings, the sea and static scenery.

        Returns (correction, normal, kind) for the deepest hit, or None."""
        best = None
        px, py = pos.x, pos.y
        i0, i1 = int((px - r) // T), int((px + r) // T)
        j0, j1 = int((py - r) // T), int((py + r) // T)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                solid = self.solid_at(i, j)
                if solid:
                    dx = px - min(max(px, i * T), (i + 1) * T)
                    dy = py - min(max(py, j * T), (j + 1) * T)
                    dist = math.hypot(dx, dy)
                    if 1e-6 <= dist < r:
                        depth = r - dist
                        if best is None or depth > best[0]:
                            best = (depth, V(dx / dist, dy / dist), "building" if solid == 1 else "sea")
        statics = self.statics
        for j in range(j0 - 1, j1 + 2):
            for i in range(i0 - 1, i1 + 2):
                for kind, p, _ in statics.get((i, j), ()):
                    dx, dy = px - p.x, py - p.y
                    dist = math.hypot(dx, dy)
                    rr = r + STATIC_RADIUS[kind]
                    if 1e-6 < dist < rr and (best is None or rr - dist > best[0]):
                        best = (rr - dist, V(dx / dist, dy / dist), kind)
        if best is None:
            return None
        depth, n, kind = best
        return n * depth, n, kind

    def nearest_road(self, p):
        """Nearest point on a road's centre line in any district, and the heading along it."""
        point, d = self.roads.nearest_point(p)
        return point, math.atan2(d.x, -d.y)

    # -- ground marks ------------------------------------------------------------
    def add_skid(self, a, b, color):
        """A skid mark from world point a to b, kept in the ground of whichever districts it crosses."""
        da = self.district_at(int(a[0] // T), int(a[1] // T))
        db = self.district_at(int(b[0] // T), int(b[1] // T))
        for d in {da, db}:
            if d is not None:
                d.add_mark(a, b, color)

    # -- drawing -----------------------------------------------------------------
    def draw_ground(self, dst, cam):
        for d in self.districts:
            d.draw_ground(dst, cam)
        for d in self.districts:
            d.draw_fresh_marks(dst, cam)

    def end_frame(self, cams):
        """Call once a frame after drawing every view: the districts' background baking."""
        views = [cam.view for cam in cams]
        for d in self.districts:
            d.end_frame(views)

    def visible_objects(self, view, extra_top=0):
        """Buildings, scenery and decorations that may show in `view`: ("building", BuildingBlock),
        ("static", kind, pos, angle), ("deco", name, depth, rect). extra_top: how far scenery can
        stand above its ground chunk."""
        out = []
        for d in self.districts:
            out += [("building", b) for b in d.visible_blocks(view)]
            objs = d.chunk_objs
            for c in d.visible_chunks(view, extra_top):
                chunk = objs.get(c)
                if chunk:
                    out += chunk
        decos = self.decos
        out += [("deco",) + decos[k] for k in view.collidelistall(self._deco_rects)]
        return out

    def draw_cables(self, dst, cam, side):
        for d in self.districts:
            d.draw_cables(dst, cam, side)

    def _build_minimap(self):
        jh = self.jh
        self.mm_rows = jh
        mm = pygame.Surface((self.iw + jh + 1, (self.iw + jh) // 2 + 1), pygame.SRCALPHA)
        for d in self.districts:
            for lj in range(d.h):
                for li in range(d.w):
                    i, j = d.ox + li, d.oy + lj
                    if d.solid[lj][li] == 1:
                        v = min(255, 90 + self.buildings[(i, j)][0].floors * 14)
                        col = (v, v - 20, v - 40)
                    else:
                        col = MINIMAP_COLORS.get(d.ground[lj][li], (75, 75, 85))
                    x, y = (i - self.i0) - (j - self.j0) + jh - 1, ((i - self.i0) + (j - self.j0)) // 2
                    mm.set_at((x, y), col)
                    mm.set_at((x + 1, y), col)
        self.minimap = mm.convert_alpha()

    def minimap_pos(self, p):
        i, j = p[0] / T - self.i0, p[1] / T - self.j0
        return V(i - j + self.mm_rows, (i + j) / 2)
