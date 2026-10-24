"""The bridge district: a suspension bridge east from the city's middle road, over open water to a
small island with a drift pad at the far end.

The deck is drawn as ground tiles at height 0; the water reads as lower because the deck's edge face
hangs down over the water tiles south of it (bridge_face overlays). Railings and towers are
decorations ("decos") depth-sorted with everything else, and the suspension cables are lines.
"""
import math

import pygame
from pygame.math import Vector2 as V

from city import BLOCKS, EDGE, road_start
from district import T, District
from iso import ZOOM, iso

DECK = 80                    # deck length in tiles, from the district's west edge
ISLAND = 16                  # tiles of island past the deck
TOWERS = (20, 60)            # deck columns of the two towers
TOWER_TOP = 160 - 12         # cable saddle height in world units (the tower sprite is 320 px tall)
RAIL_TOP = 13                # top of the railing
SAG = 18                     # lowest point of the main span's cables
CABLE = (200, 70, 44)
HANGER = (150, 52, 34)


def lay_deck(d, li, row, k):
    """One column of deck at local column li of district d: walkways on world rows row and row + 4,
    the road between. k numbers the columns along the bridge for the repeating details."""
    j0 = row - d.oy
    over_water = d.ground[j0 + 5][li] == "water"
    for dj in range(5):
        j = j0 + dj
        d.ground[j][li] = "bridge_walk" if dj in (0, 4) else "lane_x" if dj == 2 else "asphalt"
        d.solid[j][li] = 0
        ov = ["curb_s"] if dj == 0 else ["curb_n"] if dj == 4 else []
        if k % 10 == 0:
            ov.append("bridge_joint")
        if ov:
            d.overlays[(li, j)] = ov
    if not over_water:
        return
    wi = d.ox + li
    d.overlays[(li, j0 + 5)] = ["bridge_face_pier" if k % 10 == 5 and k not in TOWERS else "bridge_face"]
    # the north railing is behind everything on the deck, the south one in front of it
    d.decos.append(("rail_n", wi, row, (wi + row - 1) * T))
    d.decos.append(("rail_s", wi, row + 4, (wi + row + 7) * T))
    if k % 8 == 4:
        x = (wi + 0.5) * T
        d._add_static("lamp", V(x, (row + 0.5) * T + 11), 90)
        d._add_static("lamp", V(x, (row + 4.5) * T - 11), 270)


class Bridge(District):
    def __init__(self, city, tiles):
        super().__init__(city.ox + city.w, city.oy, DECK + ISLAND, city.h, tiles)
        self.row = road_start(BLOCKS // 2) - 1      # north walkway; the city's middle road is below it
        row = self.row
        for li in range(city.w - EDGE, city.w):      # the city's road out across its beach and sea
            lay_deck(city, li, row, li - city.w)
        for li in range(DECK):
            lay_deck(self, li, row, li)
        for k in TOWERS:
            wi = self.ox + k
            self.decos.append(("tower_n", wi, row - 1, (wi + row) * T))
            self.decos.append(("tower_s", wi, row + 5, (wi + row + 6) * T))
        self._island()
        self._cables()

    def _island(self):
        row, j0 = self.row, self.row - self.oy
        for j in range(j0 - 12, j0 + 17):
            for i in range(DECK, DECK + ISLAND - 2):
                self.ground[j][i] = "sand"
                self.solid[j][i] = 0
        for i in (DECK, DECK + 1):                   # the road runs on to the pad
            for dj in range(5):
                self.ground[j0 + dj][i] = "lane_x" if dj == 2 else "asphalt"
        x0, x1, y0, y1 = DECK + 2, DECK + 12, j0 - 9, j0 + 14
        for j in range(y0, y1):
            for i in range(x0, x1):
                self.ground[j][i] = "asphalt_crack" if (i * 7 + j * 13) % 17 == 0 else "asphalt"
        self.pad = V((self.ox + (x0 + x1) / 2) * T, (self.oy + (y0 + y1) / 2) * T)
        for k in range(12):
            a = k / 12 * math.tau
            self.prop_spots.append(("cone", self.pad + V(math.cos(a), math.sin(a)) * 72))
        for i, j, ang in ((x0, y0, 0), (x1 - 1, y0, 90), (x0, y1 - 1, 270), (x1 - 1, y1 - 1, 180)):
            self._add_static("lamp", V((self.ox + i + 0.5) * T, (self.oy + j + 0.5) * T), ang)
        for i, j in ((DECK + 1, j0 - 10), (DECK + 13, j0 + 15), (DECK + 13, j0 - 11), (DECK + 2, j0 + 15)):
            self._add_static("bush", V((self.ox + i + 0.5) * T, (self.oy + j + 0.5) * T), 0)

    def _cables(self):
        """Main cables and hangers on both sides, as un-scrolled screen points."""
        x0, x1 = self.ox * T, (self.ox + DECK) * T
        xa, xb = ((self.ox + k + 0.5) * T for k in TOWERS)
        mid, half = (xa + xb) / 2, (xb - xa) / 2

        def z(x):
            if x < xa:
                s = (x - x0) / (xa - x0)
            elif x > xb:
                s = (x1 - x) / (x1 - xb)
            else:
                s = (x - mid) / half
                return SAG + (TOWER_TOP - SAG) * s * s
            return RAIL_TOP + (TOWER_TOP - RAIL_TOP) * s * s

        def screen(x, y, h):
            p = iso((x, y))
            return p.x, p.y - h * ZOOM

        self.cables = {}
        for side, yc, yr in (("back", (self.row - 0.5) * T, (self.row + 0.05) * T),
                             ("front", (self.row + 5.5) * T, (self.row + 4.95) * T)):
            xs = [x0 + k * T / 2 for k in range(2 * DECK + 1)]
            main = [screen(x, yc, z(x)) for x in xs]
            hangers = [(screen(x, yc, z(x)), screen(x, yr, RAIL_TOP)) for x in
                       ((self.ox + k + 0.5) * T for k in range(1, DECK))
                       if abs(x - xa) > T and abs(x - xb) > T and z(x) > RAIL_TOP + 4]
            box = pygame.Rect(main[0], (0, 0)).unionall([pygame.Rect(p, (1, 1)) for p in main])
            self.cables[side] = (main, hangers, box.inflate(8, 8))

    def nearest_road(self, p):
        x = min(max(p[0], self.ox * T), (self.ox + DECK + 2) * T)
        return V(x, (self.row + 2.5) * T), math.pi / 2

    def draw_cables(self, dst, cam, side):
        main, hangers, box = self.cables[side]
        if not box.colliderect(cam.view):
            return
        ox, oy = cam.ox, cam.oy
        for a, b in hangers:
            pygame.draw.line(dst, HANGER, (a[0] - ox, a[1] - oy), (b[0] - ox, b[1] - oy))
        pygame.draw.lines(dst, CABLE, False, [(x - ox, y - oy) for x, y in main], 2 * ZOOM - 1)
