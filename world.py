"""The world: the districts side by side in one tile space, and everything the game asks of the map.

Outside every district is open sea.
"""
import pygame
from pygame.math import Vector2 as V

from bridge import Bridge
from city import City
from district import T
from iso import iso

SURFACE = {"grass": "grass", "grass_flowers": "grass", "dirt": "gravel", "sand": "gravel"}
STATIC_RADIUS = {"tree": 6, "pine": 5, "bush": 7, "lamp": 3}
MINIMAP_COLORS = {"water": (40, 90, 150), "sand": (220, 205, 150), "grass": (80, 150, 60),
                  "grass_flowers": (80, 150, 60), "dirt": (170, 140, 95), "plaza": (200, 185, 150),
                  "sidewalk": (170, 165, 155), "bridge_walk": (170, 165, 155), "park_line_x": (90, 90, 100)}


class World:
    def __init__(self, tiles, buildings, scenery, decos):
        """decos: name -> (surface, pivot) for the decorations districts place."""
        self.city = City(tiles, buildings, scenery)
        self.bridge = Bridge(self.city, tiles)
        self.districts = [self.city, self.bridge]
        for d in self.districts:
            d.finish()
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
        self.start = self.city.start
        self._build_minimap()

    # -- queries ---------------------------------------------------------------
    def district_at(self, i, j):
        for d in self.districts:
            if d.contains(i, j):
                return d
        return None

    def solid_at(self, i, j):
        d = self.district_at(i, j)
        return d.solid_w(i, j) if d else 2

    def ground_at(self, p):
        i, j = int(p[0] // T), int(p[1] // T)
        d = self.district_at(i, j)
        return d.ground_w(i, j) if d else "water"

    def surface_at(self, p):
        return SURFACE.get(self.ground_at(p), "road")

    def on_sidewalk(self, p):
        return self.ground_at(p) in ("sidewalk", "bridge_walk")

    def collide(self, pos, r):
        """Push a circle out of buildings, the sea and static scenery.

        Returns (correction, normal, kind) for the deepest hit, or None."""
        best = None
        i0, i1 = int((pos.x - r) // T), int((pos.x + r) // T)
        j0, j1 = int((pos.y - r) // T), int((pos.y + r) // T)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                solid = self.solid_at(i, j)
                if solid:
                    cx = min(max(pos.x, i * T), (i + 1) * T)
                    cy = min(max(pos.y, j * T), (j + 1) * T)
                    d = pos - V(cx, cy)
                    dist = d.length()
                    if dist < r:
                        if dist < 1e-6:
                            continue
                        depth = r - dist
                        if best is None or depth > best[0]:
                            best = (depth, d / dist, "building" if solid == 1 else "sea")
        for j in range(j0 - 1, j1 + 2):
            for i in range(i0 - 1, i1 + 2):
                for kind, p, _ in self.statics.get((i, j), ()):
                    d = pos - p
                    dist = d.length()
                    rr = r + STATIC_RADIUS[kind]
                    if 1e-6 < dist < rr and (best is None or rr - dist > best[0]):
                        best = (rr - dist, d / dist, kind)
        if best is None:
            return None
        depth, n, kind = best
        return n * depth, n, kind

    def nearest_road(self, p):
        """Centre of the nearest lane in any district, and the heading along it."""
        return min((d.nearest_road(p) for d in self.districts), key=lambda r: r[0].distance_squared_to(p))

    # -- drawing -----------------------------------------------------------------
    def draw_ground(self, dst, cam):
        for d in self.districts:
            d.draw_ground(dst, cam)

    def visible_objects(self, view, extra_top=0):
        """Buildings, scenery and decorations that may show in `view`, as the district chunks
        hold them: ("building", i, j), ("static", kind, pos, angle), ("deco", name, depth, rect)."""
        out = []
        for d in self.districts:
            for c in d.visible_chunks(view, extra_top):
                out += d.chunk_objs.get(c, ())
        out += [("deco", name, depth, rect) for name, depth, rect in self.decos if rect.colliderect(view)]
        return out

    def building_image(self, i, j, faded=False):
        return self.district_at(i, j).building_image(i, j, faded)

    def draw_cables(self, dst, cam, side):
        for d in self.districts:
            d.draw_cables(dst, cam, side)

    def _build_minimap(self):
        ds = self.districts
        self.i0, self.j0 = min(d.ox for d in ds), min(d.oy for d in ds)
        iw = max(d.ox + d.w for d in ds) - self.i0
        jh = max(d.oy + d.h for d in ds) - self.j0
        self.mm_rows = jh
        mm = pygame.Surface((iw + jh + 1, (iw + jh) // 2 + 1), pygame.SRCALPHA)
        for d in ds:
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
        self.minimap = mm

    def minimap_pos(self, p):
        i, j = p[0] / T - self.i0, p[1] / T - self.j0
        return V(i - j + self.mm_rows, (i + j) / 2)
