"""Writes every spritegen input to sprites_src/ and renders them all to assets/sprites.

Everything is laid out in code. The isometric ground tiles and building floors have 2:1 diamond
edges and slanted window rows that are easier to get exact in code than by hand; the cars,
street props and scenery are modelled as voxels and cut into sprite-stack slices.
Sprites are drawn at the game's full resolution: ZOOM (2) screen pixels per world unit.

    py tools/gen_sprites.py          # regenerate the JSON and render everything
    py tools/gen_sprites.py --json   # only rewrite the JSON
"""
import glob
import json
import math
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sprites_src")
OUT = os.path.join(ROOT, "assets", "sprites")
SPRITEGEN = r"C:\Dev\SpriteGen\publish\spritegen.exe"

sys.path.insert(0, ROOT)
from iso.paint import ramp, stripe_ramp  # noqa: E402  (shared with the game's repainting)

TILE_W, TILE_H = 128, 64  # one ground tile: a 2:1 diamond
T = 64                    # texels along a tile edge (a tile is 32 world units)
FLOOR_H = 48              # wall height of one building floor in pixels


def noise(*a):
    """Deterministic 0..1 hash noise."""
    h = 2166136261
    for v in a:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 0x5BD1E995) & 0xFFFFFFFF
    h ^= h >> 15
    return h / 2 ** 32


def vnoise(u, v, n, seed):
    """Smooth 0..1 value noise over a tile, n cells across, wrapping so repeated tiles join up."""
    x, y = u * n, v * n
    i, j = int(x), int(y)
    fx, fy = x - i, y - j
    fx, fy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
    c = lambda a, b: noise(a % n, b % n, seed)
    top = c(i, j) + (c(i + 1, j) - c(i, j)) * fx
    bot = c(i, j + 1) + (c(i + 1, j + 1) - c(i, j + 1)) * fx
    return top + (bot - top) * fy


def blank(w, h):
    return [["."] * w for _ in range(h)]


def rows(grid):
    return ["".join(r) for r in grid]


def in_diamond(x, y, w, h):
    """True if pixel (x, y) is inside a w x h (2:1) diamond whose top-left box corner is 0,0."""
    half_w, half_h = w // 2, h // 2
    dx = half_w - 1 - x if x < half_w else x - half_w
    dy = y if y < half_h else h - 1 - y
    return 0 <= x < w and 0 <= y < h and dx // 2 <= dy


def diamond_uv(x, y):
    """Local world coords (u, v) in 0..1 of a pixel in a tile diamond."""
    sx, sy = x + 0.5 - TILE_W / 2, y + 0.5
    return (sy + sx / 2) / T, (sy - sx / 2) / T


def uv_pixel(u, v):
    """Inverse of diamond_uv: the pixel a tile-local (u, v) lands on."""
    sy, sx = (u + v) / 2 * T, (u - v) * T
    return int(sx + TILE_W / 2), int(sy)


# ---------------------------------------------------------------------------
# Ground tiles
# ---------------------------------------------------------------------------

TILE_PALETTE = {
    ".": "transparent",
    "G": "#5c9e3e", "g": "#4c8a34", "q": "#3d742b", "h": "#76ba4c", "i": "#9ad466",   # grass
    "f": "#f6e27a", "p": "#f08cb0", "F": "#fbf6ee", "O": "#e0962a",                   # flowers
    "A": "#4c4c57", "a": "#44444e", "b": "#595965", "x": "#2c2c33", "X": "#3d3d47",   # asphalt
    "z": "#74747f",
    "Y": "#eac23e", "y": "#b8983a", "W": "#ecebe2", "w": "#b9b8b0",                   # road paint
    "S": "#bdb6aa", "s": "#958e83", "e": "#d2ccc0", "E": "#ada69a",                   # sidewalk
    "C": "#e4dfd4", "c": "#7c776f", "K": "#b2ac9f", "k": "#2e2d33",                   # kerb
    "P": "#d2bd9a", "Q": "#e0cca8", "J": "#a8957a", "U": "#c2ab86", "R": "#ecdcbc",   # plaza pavers
    "D": "#b08f5e", "d": "#977a4c", "r": "#c6a676", "T": "#e2cca0", "t": "#76603e",   # dirt
    "N": "#e8d69c", "n": "#d4c088", "v": "#f4e6b8",                                   # sand
    "B": "#3b7cc0", "o": "#336db0", "V": "#2a5f9c", "L": "#7ab4e6", "l": "#c8e6fa",   # water
    "m": "#2e2e35", "M": "#62626c", "H": "#8a8a94",                                   # manhole
}


def grass(u, v, x, y):
    patch = vnoise(u, v, 4, 11)
    if noise(x, y + 1, 1) > 0.91:
        return "i" if patch > 0.45 else "h"      # blade tip
    if noise(x, y, 1) > 0.91:
        return "h"                               # blade
    if noise(x, y - 1, 1) > 0.91:
        return "q"                               # its shadow
    n = noise(x, y, 8)
    if patch < 0.32:
        return "q" if n < 0.25 else "g"
    if patch > 0.7:
        return "h" if n < 0.2 else "G"
    return "g" if n < 0.2 else "G"


FLOWERS = [(0.22, 0.28, "f"), (0.68, 0.52, "p"), (0.42, 0.8, "f"), (0.82, 0.16, "p"), (0.12, 0.64, "F"),
           (0.55, 0.3, "F"), (0.86, 0.82, "f"), (0.3, 0.5, "p")]


def grass_flowers(u, v, x, y):
    for fu, fv, col in FLOWERS:
        px, py = uv_pixel(fu, fv)
        d = abs(x - px) + abs(y - py)
        if d == 0:
            return "O"
        if d == 1 and (x == px or y == py):
            return col
        if d == 2 and y == py + 1:
            return "q"                           # shadow under the head
    return grass(u, v, x, y)


def asphalt(u, v, x, y):
    n = noise(x, y, 2)
    if n > 0.988:
        return "z"                               # a pale stone in the mix
    patch = vnoise(u, v, 3, 21)
    if patch < 0.3:
        return "a" if n < 0.5 else "X" if n < 0.56 else "A"
    return "a" if n < 0.13 else "b" if n > 0.93 else "A"


def crack_v(u):
    return 0.45 + 0.12 * math.sin(u * 11)


def asphalt_crack(u, v, x, y):
    if 0.15 < u < 0.85 and abs(v - crack_v(u)) < 0.011:
        return "x"
    if 0.5 < u < 0.7 and abs(v - crack_v(u) - (u - 0.5) * 1.2) < 0.009:
        return "x"
    if 0.15 < u < 0.85 and abs(v - crack_v(u)) < 0.03:
        return "X"                               # dark seep around the crack
    return asphalt(u, v, x, y)


def manhole(u, v, x, y):
    d = math.hypot(u - 0.5, v - 0.5)
    if d < 0.12:
        if (int(u * 48) + int(v * 48)) % 4 == 0:
            return "m"                           # cast grip pattern
        return "H" if (u - 0.5) + (v - 0.5) < -0.1 else "M"
    if d < 0.135:
        return "H" if u + v < 1 else "m"         # lid rim catches the light top-left
    if d < 0.16:
        return "m"
    if d < 0.175:
        return "X"
    return asphalt(u, v, x, y)


def worn(col, x, y):
    return col.lower() if noise(x, y, 3) < 0.12 else col


def lane_x(u, v, x, y):
    if abs(v - 0.5) < 0.03 and 0.2 < u < 0.7:
        return worn("Y", x, y)
    return asphalt(u, v, x, y)


def cross_x(u, v, x, y):
    if 0.12 < u < 0.88 and (v * 4) % 1 < 0.5:
        return worn("W", x, y)
    return asphalt(u, v, x, y)


def park_line(u, v, x, y):
    if u < 0.05 and 0.08 < v:
        return worn("W", x, y)
    return asphalt(u, v, x, y)


def swap(fn):
    return lambda u, v, x, y: fn(v, u, x, y)


def sidewalk(u, v, x, y):
    fu, fv = (u * 2) % 1, (v * 2) % 1
    if fu < 0.025 or fv < 0.025:
        return "s"                               # joint
    if fu < 0.055 or fv < 0.055:
        return "e"                               # slab lip, lit from the top left
    if fu > 0.97 or fv > 0.97:
        return "E"
    slab = (int(u * 2), int(v * 2))
    if noise(*slab, 41) < 0.3:                   # a hairline crack across some slabs
        c = 0.3 + 0.4 * noise(*slab, 42)
        if abs(fv - c - (fu - 0.5) * 0.35) < 0.012:
            return "s"
    if vnoise(u, v, 6, 31) > 0.83:
        return "E"                               # old stains
    return "e" if noise(x, y, 4) < 0.07 else "S"


def plaza(u, v, x, y):
    fu, fv = (u * 4) % 1, (v * 4) % 1
    if fu < 0.06 or fv < 0.06:
        return "J"
    iu, iv = int(u * 4), int(v * 4)
    if fu < 0.14 or fv < 0.14:
        return "R" if (iu + iv) % 2 else "Q"
    if noise(iu, iv, 51) < 0.15:
        return "U"
    return "Q" if (iu + iv) % 2 else "P"


def dirt(u, v, x, y):
    if noise(x // 2, y // 2, 55) > 0.95:
        return "T" if y % 2 == 0 else "t"        # pebbles
    patch = vnoise(u, v, 5, 56)
    n = noise(x, y, 5)
    if patch < 0.3:
        return "d" if n < 0.4 else "D"
    return "d" if n < 0.18 else "r" if n > 0.9 else "D"


def sand(u, v, x, y):
    w = math.sin((u * 5 + v * 3) * math.tau + vnoise(u, v, 4, 61) * 3)
    n = noise(x, y, 6)
    if w > 0.86:
        return "v"
    if w < -0.8 or n < 0.12:
        return "n"
    return "N"


def water(u, v, x, y):
    w = math.sin((u + v) * math.tau * 3 + math.sin(u * math.tau * 2) * 1.2)
    n = noise(x, y, 7)
    if w > 0.93 and n < 0.6:
        return "l" if n < 0.08 else "L"
    if w < -0.4:
        return "V" if vnoise(u, v, 3, 71) < 0.35 else "o"
    return "B"


def curb(side):
    """Overlay: a raised kerb along one edge of a sidewalk tile, transparent elsewhere."""
    def fn(u, v, x, y):
        d = {"n": v, "s": 1 - v, "w": u, "e": 1 - u}[side]
        if d < 0.018:
            return "k"                           # gutter shadow
        if d < 0.045:
            return "c"                           # kerb face
        if d < 0.06:
            return "K"
        if d < 0.11:
            return "C"                           # kerb top
        if d < 0.125:
            return "K"
        return "."
    return fn


TILES = {
    "grass": grass,
    "grass_flowers": grass_flowers,
    "asphalt": asphalt,
    "asphalt_crack": asphalt_crack,
    "manhole": manhole,
    "lane_x": lane_x,
    "lane_y": swap(lane_x),
    "cross_x": cross_x,
    "cross_y": swap(cross_x),
    "park_line_x": park_line,
    "park_line_y": swap(park_line),
    "sidewalk": sidewalk,
    "plaza": plaza,
    "dirt": dirt,
    "sand": sand,
    "water": water,
    "curb_n": curb("n"),
    "curb_e": curb("e"),
    "curb_s": curb("s"),
    "curb_w": curb("w"),
}


def tile_frames():
    frames = []
    for name, fn in TILES.items():
        g = blank(TILE_W, TILE_H)
        for y in range(TILE_H):
            for x in range(TILE_W):
                if in_diamond(x, y, TILE_W, TILE_H):
                    u, v = diamond_uv(x, y)
                    g[y][x] = fn(min(max(u, 0.0), 0.999), min(max(v, 0.0), 0.999), x, y)
        frames.append({"name": name, "grid": rows(g)})
    return frames


# ---------------------------------------------------------------------------
# Buildings: one floor of walls per frame (128 x 112), stacked in game, roof on top
# ---------------------------------------------------------------------------

BUILDING_PALETTE = {
    ".": "transparent",
    "k": "#1c1a22",
    "f": "#ece6d8", "F": "#aaa497",            # window frames (left / right face)
    "o": "#f6f2e8", "O": "#bcb6a8",            # sills
    "q": "#3a3640", "Q": "#2a2730",            # recess and sill shadows
    "g": "#42627f", "G": "#2c4560",            # glass
    "i": "#93bee0", "I": "#5d85aa",            # glass highlight
    "y": "#ffe49a", "Y": "#d6b46e",            # lit window
    "t": "#e89a6a", "T": "#b8744c",            # curtains in lit windows
    "d": "#5e3c2a", "D": "#40291d",            # door
    "v": "#e8c862", "V": "#a88c40",            # door handle
    "u": "#8c8983", "U": "#7a7771", "K": "#6a6762", "M": "#a29f98",   # roof gravel
    "p": "#d6d2ca", "P": "#5e5b56", "+": "#ecebe6",                   # parapet top, its shadow, cap
    "a": "#d2d6dc", "A": "#a6acb4", "Z": "#7e848c", "z": "#4e545c",   # AC unit
    "-": "#353a42",
    "n": "#a4714a", "N": "#845634", "m": "#5e3c24", "~": "#3e2818",   # water tank
    "r": "#de4444", "R": "#a82e2e", "w": "#f2eee2", "W": "#bebaae",   # awning stripes
    "e": "#40a05e", "E": "#2c7442",
    "*": "#f0d050", "@": "#50a0e0", "%": "#e06080",                   # shop window goods
    "1": "#b65c42", "2": "#84422f", "3": "#9c4b36", "4": "#6c3324",   # brick
    "l": "#c66e52", "L": "#ad5a40",
    "5": "#b6b4ae", "6": "#86848c", "7": "#9e9c98", "8": "#6e6c74",   # concrete
    "c": "#e6d4a6", "C": "#b9a37a", "s": "#4f8c56", "S": "#3a6a40",   # cream + shutters
    "<": "#d8c494", ">": "#a8946c",
    "b": "#5c9ec6", "B": "#38688f", "x": "#d8dfe6", "X": "#9ca8b4",   # glass tower
    "h": "#a0cdea", "H": "#6290b8", "/": "#ffe7a6", "&": "#cfb070",
    "9": "#eaa2b6", "0": "#b8768a", "j": "#f6d2dc", "J": "#c89aa8",   # pastel
    "^": "#e08ea6", "$": "#a86478",
}

# wall (left, right), detail (left, right), awning (left, right) or None
STYLES = {
    "brick": ("12", "34", "rR"),
    "concrete": ("56", "78", "eE"),
    "cream": ("cC", "sS", "rR"),
    "pastel": ("90", "jJ", "eE"),
    "glass": ("bB", "xX", None),
}
SPECKLE = {"cream": "<>", "pastel": "^$"}


def face_px(x, y, h=FLOOR_H):
    """(is_left, u, v) if pixel (x, y) of a floor frame is on a wall face, else None.

    u runs 0..63 across the face left to right on screen, v 0..h-1 from the top of the floor."""
    left = x < 64
    dx = 63 - x if left else x - 64
    e = 63 - dx // 2          # bottom edge of the floor's top diamond in this column
    if e < y <= e + h:
        return left, (x if left else x - 64), y - e - 1
    return None


def window(u, v, u0, u1, v0, v1, side, lit, mullions=True):
    """Key for a framed window with sill covering u0..u1 x v0..v1, or None if (u, v) is outside it."""
    if v == v1 + 1 and u0 - 1 <= u <= u1 + 1:
        return "oO"[side]
    if v == v1 + 2 and u0 <= u <= u1:
        return "qQ"[side]
    if not (u0 <= u <= u1 and v0 <= v <= v1):
        return None
    if u in (u0, u1) or v in (v0, v1):
        return "fF"[side]
    if mullions and (u == (u0 + u1) // 2 or v == v0 + (v1 - v0) // 3):
        return "fF"[side]
    if u == u0 + 1 or v == v0 + 1:
        return "qQ"[side]
    if lit:
        return "tT"[side] if u - u0 <= 3 or u1 - u <= 2 else "yY"[side]
    d = (u - u0) + (v - v0)
    if 4 <= d <= 7 or 12 <= d <= 13:
        return "iI"[side]
    return "gG"[side]


def wall_px(style, kind, left, u, v, floor_seed):
    side = 0 if left else 1
    wall, detail, awning = STYLES[style]
    w, dt = wall[side], detail[side]
    lit = lambda k: noise(floor_seed, k, side) < 0.22

    if style == "glass":
        if v <= 2 or u % 16 == 0 or v % 12 == 0:
            return "xX"[side]
        if kind in ("base", "shop") and left and 24 <= u <= 39 and v >= 18:
            return "dD"[side] if u in (24, 39) or v == 18 else "gG"[side]
        pu, pv = u // 16, v // 12
        if noise(floor_seed, pu, pv, side) < 0.14:
            return "/&"[side]
        if ((u * 2 - v) % 58) < 7 or v % 12 == 1:
            return "hH"[side]
        return "bB"[side]

    if kind == "shop" and awning:
        if 6 <= v <= 15 or (v == 16 and u % 8 in (2, 3, 4, 5)):
            return (awning if (u // 8) % 2 == 0 else "wW")[side]
        if v in (17, 18) and 2 <= u <= 61:
            return "qQ"[side]
        if 4 <= u <= 59 and 20 <= v <= 44:
            if u in (4, 59) or v in (20, 44) or u == 32:
                return "fF"[side]
            if 38 <= v <= 43:
                return "*@%"[int(noise(floor_seed, u // 4, 9) * 3)]   # goods on display
            return window(u, v, 4, 59, 20, 44, side, lit(0), mullions=False)
    elif kind in ("base", "shop"):
        if left and 24 <= u <= 39 and v >= 16:
            if v >= 46:
                return "oO"[side]                # door step
            if u in (24, 39) or v == 16:
                return "fF"[side]
            if 27 <= u <= 36 and 19 <= v <= 28:
                return "gG"[side] if (u - 27) + (v - 19) > 3 else "iI"[side]
            if u == 35 and 32 <= v <= 34:
                return "vV"[side]
            return "dD"[side]
        for k_i, (u0, u1) in enumerate(((5, 18), (45, 58)) if left else ((8, 26), (36, 54))):
            k = window(u, v, u0, u1, 16, 36, side, lit(k_i))
            if k:
                return k
    elif style == "concrete":
        if 16 <= v <= 32 and 4 <= u <= 59:
            if v in (16, 32) or u % 10 == 4:
                return "fF"[side]
            if v == 17:
                return "qQ"[side]
            if lit(u // 10):
                return "tT"[side] if u % 10 in (5, 6) else "yY"[side]
            return "iI"[side] if v < 22 and (u + v) % 7 < 3 else "gG"[side]
        if v == 33 and 3 <= u <= 60:
            return "oO"[side]
        if v == 34 and 4 <= u <= 59:
            return "qQ"[side]
    else:
        for k_i, (u0, u1) in enumerate(((11, 22), (41, 52))):
            k = window(u, v, u0, u1, 10, 34, side, lit(k_i))
            if k:
                return k
            if style == "cream" and 10 <= v <= 34 and (u0 - 5 <= u <= u0 - 1 or u1 + 1 <= u <= u1 + 5):
                return "E" if v % 2 else dt         # louvred shutters
        if style == "pastel":
            if v == 38 and 4 <= u <= 59:
                return dt                         # balcony rail
            if 39 <= v <= 41 and 4 <= u <= 59 and u % 4 == 2:
                return dt
            if 42 <= v <= 43 and 2 <= u <= 61:
                return dt                         # balcony slab
            if v == 44 and 2 <= u <= 61:
                return "qQ"[side]

    # plain wall with a little texture
    if v <= 1:
        return dt                                 # cornice
    if v == 2:
        return "qQ"[side]
    if style == "brick":
        course = v // 4
        if v % 4 == 3 or (u + (4 if course % 2 else 0)) % 8 == 0:
            return dt                             # mortar
        b = noise(u // 8 + course * 31, course, side, 7)
        if b < 0.2:
            return "lL"[side]
        if b > 0.88:
            return dt
    elif style == "concrete":
        if u % 32 == 0 or v == FLOOR_H - 1:
            return dt
        if vnoise(u / 64, v / 48, 4, floor_seed) > 0.78:
            return "78"[side]
    elif style in SPECKLE and noise(u, v, floor_seed, 5) < 0.08:
        return SPECKLE[style][side]
    return w


def floor_frame(style, kind, seed):
    h = FLOOR_H
    g = blank(TILE_W, TILE_H + h)
    for y in range(TILE_H + h):
        for x in range(TILE_W):
            f = face_px(x, y)
            if f is None:
                continue
            left, u, v = f
            if kind in ("base", "shop") and v >= h - 2:
                g[y][x] = "k" if v == h - 1 else "qQ"[0 if left else 1]
            elif x in (0, TILE_W - 1) or x in (63, 64):
                g[y][x] = STYLES[style][1][0 if left else 1]   # building corners
            else:
                g[y][x] = wall_px(style, kind, left, u, v, seed + v // 60)
    return g


def roof_frame():
    """Flat gravel roof: a tile diamond in the bottom 64 rows; rooftop clutter goes above it."""
    g = blank(TILE_W, TILE_H + FLOOR_H)
    for y in range(TILE_H):
        for x in range(TILE_W):
            if in_diamond(x, y, TILE_W, TILE_H):
                n = noise(x, y, 9)
                u, v = diamond_uv(x, y)
                dark = vnoise(u, v, 3, 91) < 0.3
                g[y + FLOOR_H][x] = "K" if n < 0.08 or (dark and n < 0.3) else "U" if n < 0.25 else \
                    "M" if n > 0.94 else "u"
    return g


def rim_frame(side):
    """Parapet along one roof edge, so joined roofs of one building only get an outer rim."""
    g = blank(TILE_W, TILE_H + FLOOR_H)
    for y in range(TILE_H):
        for x in range(TILE_W):
            if in_diamond(x, y, TILE_W, TILE_H):
                u, v = diamond_uv(x, y)
                d = {"n": v, "s": 1 - v, "w": u, "e": 1 - u}[side]
                if d < 0.03:
                    g[y + FLOOR_H][x] = "+"
                elif d < 0.08:
                    g[y + FLOOR_H][x] = "p"
                elif d < 0.17 and side in "nw":
                    g[y + FLOOR_H][x] = "P"
    return g


def iso_box(g, cx, cy, hw, height, top, left, right, outline="k"):
    """Draw a small isometric box standing on the diamond centred at (cx, cy), 2*hw wide."""
    dw, dh = 2 * hw, hw
    x0, y0 = cx - hw, cy - dh // 2 - height        # top diamond's bounding box corner
    for x in range(dw):
        for y in range(dh + height):
            px, py = x0 + x, y0 + y
            if not (0 <= px < len(g[0]) and 0 <= py < len(g)):
                continue
            if y < dh and in_diamond(x, y, dw, dh):
                key = top
            else:
                lft = x < hw
                dx = hw - 1 - x if lft else x - hw
                e = dh - 1 - dx // 2
                if not (e < y <= e + height):
                    continue
                key = left if lft else right
                if y == e + height or x in (0, dw - 1):
                    key = outline
            g[py][px] = key
    return x0, y0


def roof_ac():
    g = blank(TILE_W, TILE_H + FLOOR_H)
    x0, y0 = iso_box(g, 52, FLOOR_H + 36, 16, 14, "a", "A", "Z")
    # fan grille on the lid
    for y in range(16):
        for x in range(32):
            dx, dy = (x - 15.5) / 2, y - 7.5
            d = math.hypot(dx, dy)
            if d < 5.5 and in_diamond(x, y, 32, 16):
                ang = math.atan2(dy, dx)
                g[y0 + y][x0 + x] = "z" if d > 4.6 or d < 1.2 else "-" if (ang * 3 / math.pi) % 1 < 0.45 else "Z"
    # louvres down its left face
    for x in range(x0 + 3, x0 + 14):
        for y in range(len(g)):
            if g[y][x] == "A" and y % 2 == 0:
                g[y][x] = "Z"
    iso_box(g, 82, FLOOR_H + 24, 8, 8, "a", "A", "Z")
    for y in range(FLOOR_H + 18, FLOOR_H + 30):   # duct from the small box
        for x in (70, 71, 72):
            if g[y][x] == ".":
                g[y][x] = "Z" if x < 72 else "z"
    return g


def roof_tank():
    g = blank(TILE_W, TILE_H + FLOOR_H)
    for lx, ly in ((52, 80), (76, 80), (64, 86), (64, 74)):
        for y in range(ly - 16, ly + 1):
            g[y][lx] = "k"
            g[y][lx + 1] = "z"
    x0, y0 = iso_box(g, 64, 64, 20, 24, "n", "N", "m")
    for x in range(44, 84):
        for y in range(20, 68):
            if g[y][x] in "Nm" and y % 6 == 0:   # iron hoops
                g[y][x] = "~"
            elif g[y][x] in "Nm" and x % 5 == 0:  # planks
                g[y][x] = "m" if g[y][x] == "N" else "~"
    # conical lid
    for y in range(12):
        for x in range(40):
            dx = abs(x - 19.5)
            if dx <= (y + 1) * 1.7 and y0 - 6 + y >= 0:
                g[y0 - 6 + y][x0 + x] = "n" if x < 20 else "N"
    return g


def building_frames():
    frames = []
    for si, style in enumerate(STYLES):
        for kind in ("base", "shop", "mid"):
            if kind == "shop" and STYLES[style][2] is None:
                continue
            frames.append({"name": f"{style}_{kind}", "grid": rows(floor_frame(style, kind, si * 7 + 1))})
        frames.append({"name": f"{style}_mid_b", "grid": rows(floor_frame(style, "mid", si * 7 + 4))})
    frames.append({"name": "roof", "grid": rows(roof_frame())})
    for side in "nesw":
        frames.append({"name": f"rim_{side}", "grid": rows(rim_frame(side))})
    frames.append({"name": "roof_ac", "grid": rows(roof_ac())})
    frames.append({"name": "roof_tank", "grid": rows(roof_tank())})
    return frames


# ---------------------------------------------------------------------------
# Scenery sprite stacks: 48x48 top-down slices, bottom first
# ---------------------------------------------------------------------------

SCENERY_PALETTE = {
    ".": "transparent",
    "t": "#6a4a30", "T": "#4c331e", "o": "#86603e",
    "e": "#a8de70", "E": "#7cc456", "F": "#4f9b3f", "f": "#3a7a30", "q": "#2a5c26",
    "V": "#3f8a5a", "v": "#2d6a46", "W": "#5ca872", "w": "#1f4e34", "X": "#82c890",
    "l": "#4a4e58", "L": "#6c727e", "M": "#9aa0ac", "y": "#fff2b0", "Y": "#ffd870", "Z": "#fffbe6",
    "B": "#5aa04a", "b": "#3e7e36", "h": "#86c862", "H": "#b0e080",
    "p": "#e86a8a", "P": "#f6c2d0",
}
STACK = 48
LIGHT = (-0.95, -0.32)   # world direction of the light: screen top-left in the iso view


def disc(r, shade, cx=23.5, cy=23.5, ragged=0.0, seed=0):
    g = blank(STACK, STACK)
    for y in range(STACK):
        for x in range(STACK):
            dx, dy = x + 0.5 - cx - 0.5, y + 0.5 - cy - 0.5
            d = math.hypot(dx, dy)
            edge = r + (noise(x // 2, y // 2, seed, 77) - 0.5) * ragged
            if d <= edge:
                g[y][x] = shade(dx, dy, d, x, y)
    return rows(g)


def foliage(keys, layer, layers):
    dark, mid, light, top = keys

    def shade(dx, dy, d, x, y):
        lit = (dx * LIGHT[0] + dy * LIGHT[1]) / max(d, 1) * min(1, d / 6)
        clump = noise(x // 3, y // 3, layer // 3, 13)
        s = lit * 0.55 + (layer / layers) * 0.9 - 0.35 + (clump - 0.5) * 0.6 + (noise(x, y, layer) - 0.5) * 0.25
        return dark if s < -0.2 else mid if s < 0.3 else light if s < 0.7 else top
    return shade


def stack_frames(prefix, slices):
    """slices: grids bottom first; repeats become delta frames of the previous slice."""
    frames = []
    for i, grid in enumerate(slices):
        if i and grid == slices[i - 1]:
            frames.append({"name": f"{prefix}_{i}", "base": f"{prefix}_{i - 1}"})
        else:
            frames.append({"name": f"{prefix}_{i}", "grid": grid})
    return frames


def trunk(n, w=4, flare=0, keys="ttT"):
    """n slices of a square post w texels thick, bark lit from the top left; wider at the foot."""
    out = []
    lit, mid, dark = keys
    for i in range(n):
        ww = w + (2 if i < flare else 0)
        g = blank(STACK, STACK)
        for y in range(24 - ww // 2, 24 - ww // 2 + ww):
            for x in range(24 - ww // 2, 24 - ww // 2 + ww):
                k = lit if x + y < 47 else dark
                if keys == "ttT" and noise(x, i // 2, 17) < 0.25:
                    k = "o" if k == "t" else "t"  # bark grain
                g[y][x] = k
        out.append(rows(g))
    return out


def resample(radii, n):
    """A radius profile stretched to n slices."""
    out = []
    for i in range(n):
        f = i * (len(radii) - 1) / (n - 1)
        k = min(int(f), len(radii) - 2)
        out.append((radii[k] + (radii[k + 1] - radii[k]) * (f - k)) * 2)
    return out


def scenery_frames():
    tree_r = resample([4, 6, 7.5, 8.5, 9.5, 10, 10.4, 10.4, 10, 9.5, 8.8, 8, 7, 5.8, 4.4, 2.8], 32)
    tree = trunk(16, 4, flare=2) + [disc(r, foliage("qfFE" if i < 26 else "fFEe", i, len(tree_r)),
                                         ragged=3.0, seed=i // 2) for i, r in enumerate(tree_r)]
    pine_r = resample([8.5, 7.5, 6, 4.5, 7.5, 6.5, 5, 3.5, 6, 5, 3.6, 2.6, 4.2, 3, 2, 1.2], 32)
    pine = trunk(10, 4, flare=2) + [disc(r, foliage("wvVW" if i < 28 else "vVWX", i, len(pine_r)),
                                         ragged=2.0, seed=i) for i, r in enumerate(pine_r)]
    bush_r = resample([5, 6.5, 7, 7, 6.5, 5.5, 3.5], 14)
    bush = [disc(r, foliage("bBhH", i, len(bush_r)), ragged=3.0, seed=i // 2) for i, r in enumerate(bush_r)]
    # a few blossoms on the bush's upper layers
    for i in range(8, 14):
        g = [list(r) for r in bush[i]]
        for y in range(STACK):
            for x in range(STACK):
                if g[y][x] != "." and noise(x, y, i, 23) < 0.035:
                    g[y][x] = "P" if noise(x, y, 24) < 0.4 else "p"
        bush[i] = rows(g)

    # street lamp: plinth, tapered pole, arm reaching out along +x, lamp head with a glowing lens
    lamp = trunk(4, 6, keys="MLl") + trunk(40, 3, keys="MLl")
    arm = blank(STACK, STACK)
    for x in range(23, 40):
        arm[23][x] = "M"
        arm[24][x] = "L"
        arm[25][x] = "l"
    head = [r[:] for r in arm]
    for y in range(22, 27):
        for x in range(33, 42):
            head[y][x] = "Z" if y == 24 and 35 <= x <= 39 else "y" if y < 25 else "Y"
    cap = blank(STACK, STACK)
    for y in range(21, 28):
        for x in range(32, 43):
            cap[y][x] = "M" if y < 24 else "L" if y < 26 else "l"
    lamp += [rows(head), rows(head), rows(arm), rows(arm), rows(cap), rows(cap)]

    return (stack_frames("tree", tree) + stack_frames("pine", pine)
            + stack_frames("bush", bush) + stack_frames("lamp", lamp))


# ---------------------------------------------------------------------------
# Cars: voxel models cut into 32x60 top-down slices (front at the top), bottom first.
# One texel is half a world unit, one slice one screen pixel of height.
# ---------------------------------------------------------------------------

CAR_W, CAR_L = 32, 60
BODY = "#d8343c"          # the sheet is painted red with white stripes; the game repaints it
STRIPE = "#f4f0e8"

CAR_PALETTE = {
    ".": "transparent",
    **dict(zip("01234", ramp(BODY))),            # paint: deep shadow .. specular
    **dict(zip("567", stripe_ramp(STRIPE))),     # stripes: shadow, base, light
    "g": "#1c2a3e", "G": "#34506e", "h": "#7fa8c8", "H": "#d2ecff",   # glass
    "b": "#1e1d24", "B": "#3a3a44", "j": "#55555f",                   # black trim, grille mesh
    "k": "#141317", "t": "#2a2a30", "q": "#46464e",                   # tyre tread, sidewall, wear
    "c": "#5e636e", "C": "#a8b0bc", "W": "#eef2f8",                   # rim / chrome
    "l": "#8e9aa8", "L": "#fff8d8", "y": "#ffd25a",                   # headlight housing, lens, DRL
    "r": "#7a1018", "R": "#ff3a30", "a": "#ff9a2a",                   # tail lights, indicator
    "p": "#e8e6dc", "u": "#18171c",                                   # plate, underbody
}

CARS = {
    # the player's sport coupe: flared arches, fastback, wing, twin stripes, hood vents
    "coupe": dict(
        nz=23, front=1.0, rear=59.0, nose_r=7.0, tail_r=4.0, wheels=(13.0, 46.5), flare=True,
        profile=[(1, 6.5), (2.5, 8.5), (5, 10), (19, 11), (21, 11.6), (29, 19.6), (31, 20.4), (37, 20.4),
                 (40, 19.6), (49, 13.2), (55, 12.6), (57.5, 11), (59, 8)],
        belt=11.6, hood_w=5.5, roof_w=8.0, glass_w=11.0, side_glass=(23.5, 41.5), b_pillar=None,
        seams=(22.5, 39.5), handle=37.5, stripes=True, vents=True, spoiler=True, side_intake=True,
        tail="bar", headlight=(7, 8), chrome_belt=False),
    # traffic saloon: upright cabin with a B-pillar, notch-back boot, chrome belt line
    "sedan": dict(
        nz=24, front=1.0, rear=59.0, nose_r=5.0, tail_r=4.0, wheels=(12.5, 47.0), flare=False,
        profile=[(1, 7.5), (2.5, 9.5), (5, 11), (16, 12), (18, 12.6), (25, 21.2), (27, 22.2), (39, 22.2),
                 (41, 21.4), (46.5, 14.2), (48, 13.6), (56, 13.2), (58, 11.5), (59, 9)],
        belt=12.6, hood_w=6.0, roof_w=8.5, glass_w=11.0, side_glass=(19.5, 44.5), b_pillar=32.5,
        seams=(18.5, 32.5, 45.5), handle=(30.0, 42.5), stripes=False, vents=False, spoiler=False,
        side_intake=False, tail="corners", headlight=(8, 9), chrome_belt=True),
    # traffic hatchback: short nose, tall cabin, near-vertical tailgate with a little roof spoiler
    "hatch": dict(
        nz=25, front=3.0, rear=56.0, nose_r=6.0, tail_r=3.0, wheels=(13.5, 45.0), flare=False,
        profile=[(3, 8), (4.5, 10), (7, 11.5), (15, 12.6), (17, 13.2), (24, 22), (26, 23.2), (48, 23.2),
                 (50, 22.6), (53.5, 15), (55, 12.5), (56, 10)],
        belt=13.2, hood_w=6.0, roof_w=8.5, glass_w=11.0, side_glass=(18.5, 47.5), b_pillar=32.5,
        seams=(17.5, 32.5), handle=30.0, stripes=False, vents=False, spoiler=False,
        side_intake=False, tail="tall", headlight=(8, 10), chrome_belt=False),
}

WHEEL_R = 5.5             # in texels, both along the car and up
RIM_R = 3.9
TYRE_X = (1, 2, 3, 4)     # tyre columns on the left; the right side mirrors them


def smooth(e0, e1, t):
    s = min(1.0, max(0.0, (t - e0) / (e1 - e0)))
    return s * s * (3 - 2 * s)


def interp(points, y):
    if y <= points[0][0]:
        return points[0][1]
    for (y0, h0), (y1, h1) in zip(points, points[1:]):
        if y <= y1:
            return h0 + (h1 - h0) * (y - y0) / (y1 - y0)
    return points[-1][1]


class CarModel:
    """A car body as a height field over its top-down footprint, with wheels, mirrors and extras."""

    def __init__(self, m):
        self.m = m
        self.nz = m["nz"]
        self.height = [[self._height(x, y) for x in range(CAR_W)] for y in range(CAR_L)]

    def half_width(self, yc):
        m = self.m
        if not m["front"] <= yc <= m["rear"]:
            return -1.0
        w = 12.5
        if m["flare"]:
            for wy in m["wheels"]:
                w = max(w, 12.5 + smooth(9.5, 6.0, abs(yc - wy)))
        for t, rc in ((yc - m["front"], m["nose_r"]), (m["rear"] - yc, m["tail_r"])):
            if t < rc:
                w = (w - rc) + math.sqrt(max(0.0, rc * rc - (rc - t) ** 2))
        return w

    def belt(self, yc):
        m = self.m
        b = m["belt"]
        if m["flare"]:
            for wy in m["wheels"]:
                b += 1.1 * smooth(8.0, 3.5, abs(yc - wy))
        return min(b, interp(m["profile"], yc) + (1.2 if m["flare"] else 0.4))

    def _height(self, x, y):
        m = self.m
        yc = y + 0.5
        w = self.half_width(yc)
        dx = abs(x + 0.5 - CAR_W / 2)
        if dx > w:
            return 0.0
        hc = interp(m["profile"], yc)
        belt = self.belt(yc)
        if hc > belt:   # through the cabin: crowned roof, sloping side glass, shoulder
            rw, gw = m["roof_w"], m["glass_w"]
            if dx <= rw:
                h = hc - 0.7 * (dx / rw) ** 2
            elif dx <= gw:
                h = belt + (hc - 0.7 - belt) * (1 - (dx - rw) / (gw - rw))
            else:
                h = belt
            h = max(h, belt)
        else:           # bonnet / boot dipping between the wings
            h = hc + (belt - hc) * smooth(m["hood_w"], w - 1.5, dx)
        return h - 1.3 * smooth(1.6, 0.0, w - dx)

    def top(self, x, y):
        """Top body cell of a column (-1 if empty)."""
        if not (0 <= x < CAR_W and 0 <= y < CAR_L):
            return -1
        return round(self.height[y][x]) - 1

    def wheel(self, yc):
        return min(self.m["wheels"], key=lambda wy: abs(yc - wy))

    def is_body(self, x, y, z):
        if not (0 <= x < CAR_W and 0 <= y < CAR_L):
            return False
        if not 2 <= z <= self.top(x, y):
            return False
        wy = self.wheel(y + 0.5)
        if math.hypot(y + 0.5 - wy, z + 0.5 - WHEEL_R) < WHEEL_R + 0.8:
            col = min(x, CAR_W - 1 - x)
            if col <= TYRE_X[-1]:
                return False
        return True

    def slope(self, yc):
        p = self.m["profile"]
        return interp(p, yc + 1.5) - interp(p, yc - 1.5)

    # -- colouring ---------------------------------------------------------
    def body_key(self, x, y, z):
        m = self.m
        yc = y + 0.5
        dx = abs(x + 0.5 - CAR_W / 2)
        top = self.top(x, y)
        bl = round(self.belt(yc))
        hc = interp(m["profile"], yc)
        cabin = z >= bl and hc > bl + 0.5 and dx <= m["glass_w"] + 0.5
        wy = self.wheel(yc)
        arch = math.hypot(yc - wy, z + 0.5 - WHEEL_R)
        if arch < WHEEL_R + 0.8 and min(x, CAR_W - 1 - x) == TYRE_X[-1] + 1:
            return "u"                                   # inside of the wheel arch
        front = not self.is_body(x, y - 1, z)
        rear = not self.is_body(x, y + 1, z)
        side = not self.is_body(x - 1, y, z) or not self.is_body(x + 1, y, z)
        stripe = m["stripes"] and 1.0 <= dx <= 3.6

        if cabin:
            return self.cabin_key(x, y, z, dx, top, bl, hc)
        if z == top:
            return self.top_key(x, y, dx, stripe)
        if front and yc < m["front"] + m["nose_r"] + 1:
            return self.front_key(x, z, dx, stripe)
        if rear and yc > m["rear"] - m["tail_r"] - 2:
            return self.rear_key(x, z, dx)
        # side faces, and hidden cells coloured as if they were, so the rotated nearest-neighbour
        # sampling never picks out dark interior specks along the flanks
        return self.side_key(yc, z, bl, arch)

    def cabin_key(self, x, y, z, dx, top, bl, hc):
        m = self.m
        yc = y + 0.5
        s = self.slope(yc)
        zone = "ws" if s > 1.2 else "rear" if s < -1.2 else "roof"
        g0, g1 = m["side_glass"]
        if dx <= m["roof_w"] - 0.5:
            if z != top:
                return "g"                               # hidden, but stray samples show glass
            if zone == "roof":
                if m["stripes"] and 1.0 <= dx <= 3.6:
                    return "7"
                return "4" if dx in (5.5, 6.5) else "3"
            if dx > m["roof_w"] - 1.6:
                return "1"                               # A / C pillar
            if zone == "ws":
                v = (x + 2 * y) % 17
                return "H" if v < 1.5 else "h" if v < 3.5 else "G"
            v = (x - 2 * y) % 15
            return "h" if v < 1.5 else "G" if v < 3.5 else "g"
        # the sloping side glass and its frame
        if m["chrome_belt"] and z == bl:
            return "C"
        in_glass = g0 <= yc <= g1 and z < hc - 1.5 and z > bl
        if m["b_pillar"] is not None and abs(yc - m["b_pillar"]) < 1.0:
            in_glass = False
        if in_glass:
            if z >= hc - 2.5:
                return "G"
            return "h" if (y + z) % 11 == 0 else "g"
        if z == bl and g0 <= yc <= g1:
            return "b"
        return "2" if z == top else "1"

    def top_key(self, x, y, dx, stripe):
        m = self.m
        yc = y + 0.5
        h = self.height
        get = lambda xx, yy: h[yy][xx] if 0 <= xx < CAR_W and 0 <= yy < CAR_L else 0.0
        grad = math.hypot(get(x + 1, y) - get(x - 1, y), get(x, y + 1) - get(x, y - 1)) / 2
        # lamps seen from above on the nose and tail corners
        if yc < m["front"] + 3.2 and 7.0 <= dx <= 11.5:
            return "L" if dx < 10.5 else "l"
        if yc > m["rear"] - 2.2 and 8.5 <= dx <= 12.5:
            return "R" if m["tail"] != "bar" or dx > 9.5 else "r"
        if m["vents"] and 9.0 <= yc <= 14.0 and 6.0 <= dx <= 8.0:
            return "0" if y % 2 == 0 else "2"
        if stripe:
            return "7" if grad < 0.45 else "6" if grad < 0.9 else "5"
        if grad < 0.45:
            return "4" if dx in (5.5, 6.5) and yc < m["front"] + 22 else "3"
        return "2" if grad < 0.95 else "1"

    def front_key(self, x, z, dx, stripe):
        hl0, hl1 = self.m["headlight"]
        if z <= 3:
            return "b"
        if hl0 <= z <= hl1 and 6.5 <= dx <= 11.5:
            return "y" if z == hl0 else "L"
        if 4 <= z <= 6 and dx <= 6.5:
            return "j" if (x + z) % 2 else "b"           # grille mesh
        if 4 <= z <= 5 and 8.0 <= dx <= 11.5:
            return "b"
        if stripe and z > 6:
            return "6"
        return "2"

    def rear_key(self, x, z, dx):
        tail = self.m["tail"]
        if z <= 4:
            if 3 <= z <= 4 and 4.5 <= dx <= 6.5:
                return "W" if z == 4 else "C"            # exhaust tips
            return "b"
        if 5 <= z <= 6 and dx <= 3.6:
            return "p"                                   # number plate
        if tail == "bar" and 8 <= z <= 9 and dx <= 12.5:
            return "R" if z == 9 or dx > 10 else "r"
        if tail == "corners" and 8 <= z <= 10 and 8.5 <= dx <= 12.5:
            return "a" if z == 8 else "R"
        if tail == "tall" and 9 <= z <= 13 and 9.5 <= dx <= 12.5:
            return "R" if z % 2 else "r"
        return "1"

    def side_key(self, yc, z, bl, arch):
        m = self.m
        if arch < WHEEL_R + 1.7:
            return "0"                                   # wheel arch lip
        if z <= 3:
            return "b"                                   # side skirt
        if z == 4:
            return "0"
        seams = m["seams"]
        handles = m["handle"] if isinstance(m["handle"], tuple) else (m["handle"],)
        if any(abs(yc - s) < 0.5 for s in seams) and z < bl:
            return "0"
        if any(abs(yc - hy) < 1.0 for hy in handles) and z == bl - 2:
            return "C"
        if m["side_intake"] and 21.0 <= yc <= 24.0 and 6 <= z <= 8:
            return "b" if z != 7 else "j"
        if yc < m["front"] + 6 and z == m["headlight"][0]:
            return "a"                                   # front side marker
        if m["chrome_belt"] and z == bl - 1:
            return "C"
        if z == bl - 1:
            return "3"                                   # shoulder crease catches the light
        return "1" if z <= 6 else "2"

    def tyre_key(self, x, y, z):
        col = min(x, CAR_W - 1 - x)
        if col not in TYRE_X:
            return None
        wy = self.wheel(y + 0.5)
        dy, dz = y + 0.5 - wy, z + 0.5 - WHEEL_R
        r = math.hypot(dy, dz)
        if r > WHEEL_R:
            return None
        if col == TYRE_X[0]:
            if r < 1.2:
                return "C"                               # hub
            if r < RIM_R - 0.6:
                a = math.atan2(dz, dy) / math.tau * 5
                return "W" if (a % 1) < 0.34 else "c"    # five spokes
            if r < RIM_R:
                return "C"                               # rim lip
            return "t" if r < WHEEL_R - 0.8 else "k"
        return "q" if z + 0.5 > WHEEL_R + WHEEL_R * 0.75 else "k"

    def extras(self, vox):
        m = self.m
        nz = self.nz

        def put(x, y, z, k):
            if 0 <= x < CAR_W and 0 <= y < CAR_L and 0 <= z < nz:
                vox[z][y][x] = k
                vox[z][y][CAR_W - 1 - x] = k

        # door mirrors on short stalks, glass facing back
        my = m["side_glass"][0] + 0.5
        y0 = int(my)
        bl = round(self.belt(my))
        for x in (1, 2):
            for y in (y0, y0 + 1):
                put(x, y, bl, "1")
                put(x, y, bl + 1, "3" if y == y0 else "h")
        if m["spoiler"]:
            ys = range(52, 56)
            wz = 15
            for y in ys:
                for x in range(3, 16):
                    put(x, y, wz, "3" if y < 55 else "1")
                    put(x, y, wz - 1, "1" if y < 55 else "0")
            for y in range(51, 57):                      # end plates
                for z in range(wz - 2, wz + 2):
                    put(3, y, z, "0" if z < wz else "2")
            for y in (53, 54):                           # struts
                for z in range(self.top(9, y) + 1, wz - 1):
                    put(9, y, z, "b")
        if m["tail"] == "tall":                          # roof spoiler over the tailgate
            for y in (48, 49):
                for x in range(6, 16):
                    put(x, y, self.top(15, 47) + 1, "1" if y == 49 else "2")

    def voxels(self):
        nz = self.nz
        vox = [[["."] * CAR_W for _ in range(CAR_L)] for _ in range(nz)]
        for z in range(nz):
            for y in range(CAR_L):
                for x in range(CAR_W):
                    if self.is_body(x, y, z):
                        vox[z][y][x] = self.body_key(x, y, z)
                    else:
                        k = self.tyre_key(x, y, z)
                        if k:
                            vox[z][y][x] = k
        self.extras(vox)
        return vox


def car_frames():
    frames = []
    for name, m in CARS.items():
        vox = CarModel(m).voxels()
        frames += stack_frames(name, [rows(layer) for layer in vox])
    return frames


# ---------------------------------------------------------------------------
# Street props: knock-over sprite stacks, 24x24 top-down slices, bottom first
# ---------------------------------------------------------------------------

PROP = 24
PROPS_PALETTE = {
    ".": "transparent",
    "b": "#2a2226", "B": "#3e3438", "x": "#1a1518",                   # cone base
    "o": "#f2762a", "O": "#ffb070", "q": "#c04e18", "Q": "#8e3410",   # cone
    "w": "#f4f0e8", "W": "#ffffff", "v": "#b8b4b0",                   # reflective bands
    "R": "#d23a32", "e": "#ff8070", "E": "#ffc0a8", "r": "#8e2224", "s": "#5e161a",   # hydrant
    "c": "#c8ccd4", "C": "#eef0f4", "p": "#6e6e78",                   # metal
    "N": "#3e8a4c", "n": "#6ab872", "M": "#285a34", "m": "#1c4226",   # bin
    "L": "#3a3e46", "l": "#5c626c", "h": "#808894",
}


def prop_slice(fn):
    g = blank(PROP, PROP)
    for y in range(PROP):
        for x in range(PROP):
            dx, dy = x + 0.5 - PROP / 2, y + 0.5 - PROP / 2
            k = fn(dx, dy, math.hypot(dx, dy))
            if k:
                g[y][x] = k
    return rows(g)


def lit(dx, dy, d):
    """-1 (away from the light) .. 1 (facing it) for a point on a round prop."""
    return (dx * LIGHT[0] + dy * LIGHT[1]) / max(d, 0.5)


def tone(dx, dy, d, keys, edge=None):
    """Shade a round surface: keys = (shadow, base, light[, deep])."""
    s = lit(dx, dy, d)
    if s > 0.45:
        return keys[2]
    if s < -0.55 and len(keys) > 3:
        return keys[3]
    return keys[0] if s < -0.15 else keys[1]


def props_frames():
    frames = []
    # traffic cone: rubber foot, tapering cone with two reflective bands, rounded tip
    cone = []
    for z in range(17):
        if z < 2:
            cone.append(prop_slice(lambda dx, dy, d: ("B" if dx + dy < 0 else "b") if max(abs(dx), abs(dy)) < 10
                                   and abs(dx) + abs(dy) < 17 else None))
            continue
        r = 7.6 - (z - 2) * 0.42
        band = z in (6, 7, 11, 12)
        cone.append(prop_slice(lambda dx, dy, d, r=r, band=band:
                               (tone(dx, dy, d, "vwW") if band else tone(dx, dy, d, "qoOQ")) if d <= r else None))
    frames += stack_frames("cone", cone)

    # fire hydrant: base flange, barrel, side outlets with caps, bonnet and operating nut
    hyd = []
    for z in range(19):
        def f(dx, dy, d, z=z):
            if z < 2:
                return tone(dx, dy, d, "rRe", "s") if d <= 6 else None
            if 6 <= z <= 8 and abs(dy) <= 1.6 and abs(dx) <= 7.5:
                if abs(dx) > 6:
                    return "C" if z == 8 else "c"          # outlet caps
                return tone(dx, dy, d, "rRe")
            if 8 <= z <= 9 and abs(dx) <= 1.6 and -7 <= dy <= 0:
                return "c" if dy < -5.5 else tone(dx, dy, d, "rRe")   # front pumper outlet
            if z <= 12:
                return tone(dx, dy, d, "rReE"[:3] + "s") if d <= 4.4 else None
            if z <= 13:
                return tone(dx, dy, d, "rRe") if d <= 5.6 else None   # bonnet flange
            r = [4.6, 3.8, 2.8, 1.8][min(3, z - 14)] if z < 18 else 1.2
            if z == 18:
                return "C" if d <= r else None
            return tone(dx, dy, d, "rReE") if d <= r else None
        hyd.append(prop_slice(f))
    frames += stack_frames("hydrant", hyd)

    # litter bin: dark foot, ribbed body, rim and a domed lid with a handle
    bin_ = []
    for z in range(19):
        def f(dx, dy, d, z=z):
            if z == 0:
                return "m" if d <= 6.6 else None
            if z <= 14:
                if d > 7:
                    return None
                rib = (math.atan2(dy, dx) / math.tau * 16) % 1 < 0.22
                if z in (3, 11):
                    return "M"                              # hoops
                k = tone(dx, dy, d, "MNnm")
                return "M" if rib and k != "m" else k
            if z == 15:
                return tone(dx, dy, d, "lLh") if d <= 7.6 else None
            r = [7, 5.5, 3.5][z - 16] if z < 18 else 0
            if z == 18:
                return "h" if abs(dx) < 2.5 and abs(dy) < 0.8 else None
            return tone(dx, dy, d, "lLh") if d <= r else None
        bin_.append(prop_slice(f))
    frames += stack_frames("bin", bin_)
    return frames


# ---------------------------------------------------------------------------
# Effects, 32x32: tyre smoke puff
# ---------------------------------------------------------------------------

FX = 32
FX_PALETTE = {
    ".": "transparent",
    "Z": "#ffffffd8", "z": "#f4f4f6d0", "S": "#d6d6dcc0", "s": "#a8a8b4b0", "u": "#8a8a98a0",
}


def smoke_frame(puffs, holes=0.0, seed=0):
    g = blank(FX, FX)
    for y in range(FX):
        for x in range(FX):
            best = None
            for cx, cy, r in puffs:
                dx, dy = x + 0.5 - cx, y + 0.5 - cy
                d = math.hypot(dx, dy) + (noise(x, y, seed) - 0.5) * 1.2
                if d <= r:
                    s = (dx * -0.7 + dy * -0.7) / max(r, 1) + (1 - d / r) * 0.4
                    best = max(best if best is not None else -9, s)
            if best is None or noise(x // 2, y // 2, seed, 3) < holes:
                continue
            g[y][x] = "Z" if best > 0.75 else "z" if best > 0.4 else "S" if best > -0.1 else "s" if best > -0.5 else "u"
    return rows(g)


def fx_frames():
    frames = [
        {"name": "smoke_0", "grid": smoke_frame([(16, 17, 5.5), (13, 15, 3.5)], seed=1)},
        {"name": "smoke_1", "grid": smoke_frame([(16, 17, 8), (11, 14, 5), (20, 13, 4.5)], seed=2)},
        {"name": "smoke_2", "grid": smoke_frame([(16, 17, 11), (9, 12, 6.5), (22, 11, 6), (15, 8, 5)], seed=3)},
        {"name": "smoke_3", "grid": smoke_frame([(16, 17, 12.5), (8, 11, 7), (23, 10, 6.5), (15, 6, 5.5)],
                                                holes=0.35, seed=4)},
    ]
    return frames


# ---------------------------------------------------------------------------
# Bridge: deck tiles and overlays (128x64), railings and the suspension towers.
# Raised parts are boxes ray-cast through the iso view: u, v in tiles from the frame's anchor
# (the top corner of its ground tile), z in pixels. Every frame's pivot is that anchor.
# ---------------------------------------------------------------------------

BRIDGE_PALETTE = {
    ".": "transparent",
    "S": "#bdb6aa", "s": "#958e83", "l": "#d2ccc0", "E": "#ada69a",   # walkway slabs
    "C": "#dcd7ca", "c": "#aaa496", "D": "#7d786f", "d": "#56524c",   # concrete: top, left, right, deep
    "h": "#f29458", "O": "#c8462c", "o": "#8e2e1e", "q": "#5a1a12",   # orange steel: top, left, right, deep
    "m": "#3a3a42", "M": "#8a8a94", "x": "#26262c",                   # expansion joint
    "w": "#0a1e4a55", "W": "#0a1e4a99",                               # shade on the water
    "f": "#e8f4fa", "F": "#a8d0ec",                                   # foam
    "r": "#ff3a30", "R": "#ffd0c0",                                   # aircraft warning lamp
}
TOWER_H = 320             # tower height in pixels
TOWER_SPAN = 6            # tiles from the north leg to the south leg


def bridge_walk(u, v, x, y):
    fu = (u * 2) % 1
    if fu < 0.025:
        return "s"                               # slab joint across the walkway
    if fu < 0.05:
        return "l"
    if fu > 0.975:
        return "E"
    if vnoise(u, v, 5, 131) > 0.8:
        return "E"
    return "l" if noise(x, y, 132) < 0.06 else "S"


def bridge_face(pier):
    """Overlay for the water tile south of the deck: the deck's edge face hanging down over the water
    (v * T is the drop below the deck edge in pixels), its shade, and on some tiles a pier."""
    def fn(u, v, x, y):
        d = v * T
        a = u - v                                # where along the deck edge this pixel column hangs
        if d < 1.5:
            return "C"                           # lip of the deck
        if d < 13:
            return "d" if 9.5 <= d < 10.5 or d >= 12 else "c"
        if pier and 0.4 <= a <= 0.6 and d < 52:
            if d > 47:
                return "f" if noise(x, y, 133) < 0.5 else "F"
            return "D" if a > 0.55 else "C" if a < 0.43 else "c"
        if pier and 0.6 < a <= 0.78 and d < 50:
            return "W"                           # the pier's shadow
        if d < 20:
            return "W"
        if d < 34:
            return "w"
        return "."
    return fn


def bridge_joint(u, v, x, y):
    """Overlay: a finger expansion joint across the deck along the tile's u = 0 edge."""
    if u < 0.03:
        return "x"
    if u < 0.07:
        return "M" if (v * 12) % 1 < 0.5 else "m"
    if u < 0.09:
        return "m"
    return "."


def raycast(w, h, ox, oy, boxes):
    """Draw boxes (u0, u1, v0, v1, z0, z1, paint) into a w x h frame whose anchor is at (ox, oy).

    paint(face, u, v, z) gives the key for the visible point; face is "t" (top), "l" (the +y face,
    lower left on screen) or "r" (the +x face, lower right). Nearest box wins."""
    g = blank(w, h)
    for y in range(h):
        for x in range(w):
            sx, sy = x + 0.5 - ox, y + 0.5 - oy
            ug, vg = (sy + sx / 2) / T, (sy - sx / 2) / T   # ground point under the pixel
            best = None
            for u0, u1, v0, v1, z0, z1, paint in boxes:
                # the view ray is (ug + t, vg + t, z = t * T); the visible point is where it leaves the box
                lo = max(u0 - ug, v0 - vg, z0 / T)
                hi, face = min((u1 - ug, "r"), (v1 - vg, "l"), (z1 / T, "t"))
                if hi >= lo and (best is None or hi > best[0]):
                    best = (hi, paint(face, ug + hi, vg + hi, hi * T))
            if best:
                g[y][x] = best[1]
    return g


def concrete(face, u, v, z):
    return {"t": "C", "l": "c", "r": "D"}[face]


def steel(face, u, v, z):
    return {"t": "h", "l": "O", "r": "o"}[face]


def rail_frames():
    w, h, ox, oy = TILE_W, TILE_H + 30, TILE_W // 2, 30
    frames = []
    for side in "ns":
        v0 = 0.0 if side == "n" else 0.93
        boxes = [(0, 1, v0, v0 + 0.07, 0, 6, concrete),             # kerb the railing stands on
                 (0, 1, v0 + 0.02, v0 + 0.05, 22, 26, steel),       # hand rail
                 (0, 1, v0 + 0.025, v0 + 0.045, 13, 15, steel)]     # mid rail
        for k in range(4):
            boxes.append((k / 4 + 0.1, k / 4 + 0.135, v0 + 0.015, v0 + 0.055, 6, 22, steel))
        frames.append({"name": f"rail_{side}", "grid": rows(raycast(w, h, ox, oy, boxes)), "pivot": [ox, oy]})
    return frames


def tower_paint(cu, cv):
    """Orange steel leg centred on (cu, cv), with a recessed panel line down each face and
    a band every 40 pixels."""
    def paint(face, u, v, z):
        if face == "t":
            return "r" if abs(u - cu) < 0.05 and abs(v - cv) < 0.05 and z > TOWER_H - 1 else "h"
        k = steel(face, u, v, z)
        if z % 40 < 3:
            return "q" if face == "r" else "o"
        if abs((u if face == "l" else v) - (cu if face == "l" else cv)) < 0.02:
            return "q" if face == "r" else "o"
        return k
    return paint


def tower_leg(dv):
    c = 0.5
    return [(0.18, 0.82, 0.18 + dv, 0.82 + dv, 0, 14, concrete),        # footing in the water
            (0.3, 0.7, 0.3 + dv, 0.7 + dv, 14, 180, tower_paint(c, c + dv)),
            (0.34, 0.66, 0.34 + dv, 0.66 + dv, 180, TOWER_H, tower_paint(c, c + dv))]


def tower_frames():
    """The north leg carries the two cross beams over the deck; the south leg is drawn on its own,
    later, so cars on the deck pass between them. Both frames share one canvas."""
    ox, oy = 432, 310
    w, h = 472, 556
    beam = lambda z0, z1: (0.4, 0.6, 0.5, 0.5 + TOWER_SPAN, z0, z1, steel)
    north = tower_leg(0) + [beam(TOWER_H - 40, TOWER_H - 14), beam(176, 196)]
    south = tower_leg(TOWER_SPAN)
    return [{"name": "tower_n", "grid": rows(raycast(w, h, ox, oy, north)), "pivot": [ox, oy]},
            {"name": "tower_s", "grid": rows(raycast(w, h, ox, oy, south)),
             "pivot": [ox - TOWER_SPAN * TILE_W // 2, oy + TOWER_SPAN * TILE_H // 2]}]


def bridge_tile_frames():
    frames = []
    for name, fn in (("bridge_walk", bridge_walk), ("bridge_face", bridge_face(False)),
                     ("bridge_face_pier", bridge_face(True)), ("bridge_joint", bridge_joint)):
        g = blank(TILE_W, TILE_H)
        for y in range(TILE_H):
            for x in range(TILE_W):
                if in_diamond(x, y, TILE_W, TILE_H):
                    u, v = diamond_uv(x, y)
                    g[y][x] = fn(min(max(u, 0.0), 0.999), min(max(v, 0.0), 0.999), x, y)
        frames.append({"name": name, "grid": rows(g)})
    return frames


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_json(name, comment, palette, frames, columns, extra=None):
    out = ["{", f"  // {comment}", '  "palette": {']
    items = list(palette.items())
    for i, (k, v) in enumerate(items):
        out.append(f'    {json.dumps(k)}: {json.dumps(v)}' + ("," if i < len(items) - 1 else ""))
    out.append("  },")
    out.append('  "cellSize": 1,')
    out.append(f'  "columns": {columns},')
    for k, v in (extra or {}).items():
        out.append(f'  {json.dumps(k)}: {json.dumps(v)},')
    out.append('  "frames": [')
    for i, f in enumerate(frames):
        tail = "," if i < len(frames) - 1 else ""
        if "grid" in f:
            pivot = f', "pivot": {json.dumps(f["pivot"])}' if "pivot" in f else ""
            out.append(f'    {{ "name": {json.dumps(f["name"])}{pivot}, "grid": [')
            out.append(",\n".join(f"      {json.dumps(r)}" for r in f["grid"]))
            out.append(f"    ]}}{tail}")
        else:
            out.append(f'    {json.dumps(f)}{tail}')
    out.append("  ]")
    out.append("}")
    with open(os.path.join(SRC, name + ".json"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


def main():
    os.makedirs(SRC, exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    write_json("tiles", "Isometric ground tiles, 128x64 diamonds (generated by tools/gen_sprites.py). "
               "curb_* are overlays for sidewalk edges that meet the road.",
               TILE_PALETTE, tile_frames(), 8)
    write_json("buildings", "Building floors, 128x112: walls of one 48px floor under a tile diamond "
               "(generated by tools/gen_sprites.py). Stack base/shop + mid floors, then roof, rims and clutter.",
               BUILDING_PALETTE, building_frames(), 8, {"pivot": [64, 80]})
    write_json("scenery_stack", "Tree, pine, bush and street lamp sprite stacks, 48x48 top-down slices, "
               "bottom first (generated by tools/gen_sprites.py).",
               SCENERY_PALETTE, scenery_frames(), 16)
    write_json("car_stack", "Car sprite stacks: coupe (player), sedan and hatch (traffic), 32x60 top-down "
               "slices, front at the top, bottom first (generated by tools/gen_sprites.py). Paint 0-4 and "
               "stripes 5-7 are repainted in game with the iso.paint ramps.",
               CAR_PALETTE, car_frames(), 25, {"pivot": [CAR_W // 2, CAR_L // 2]})
    write_json("props_stack", "Knock-over street props as sprite stacks, 24x24 top-down slices, bottom first "
               "(generated by tools/gen_sprites.py): cone_0..16, hydrant_0..18, bin_0..18.",
               PROPS_PALETTE, props_frames(), 19)
    write_json("fx", "Effects, 32x32 (generated by tools/gen_sprites.py): tyre smoke puff smoke_0..3 "
               "(grows, then breaks up).",
               FX_PALETTE, fx_frames(), 4,
               {"animations": {"smoke": {"frames": [0, 1, 2, 3], "fps": 6}}})
    write_json("bridge_tiles", "Bridge deck tiles and overlays, 128x64 diamonds (generated by tools/gen_sprites.py): "
               "walkway, the deck edge face hanging over the water south of the deck (plain and with a pier), "
               "and an expansion joint.", BRIDGE_PALETTE, bridge_tile_frames(), 4)
    write_json("bridge_rails", "Bridge railings along the north and south edge of a deck tile, 128x94 "
               "(generated by tools/gen_sprites.py). Pivot: the tile's top corner.",
               BRIDGE_PALETTE, rail_frames(), 2)
    write_json("bridge_towers", "Suspension bridge tower, 472x556 (generated by tools/gen_sprites.py): tower_n is "
               "the north leg with the cross beams, tower_s the south leg six tiles south. Pivot: the top "
               "corner of each leg's tile.", BRIDGE_PALETTE, tower_frames(), 2)
    if "--json" in sys.argv:
        return
    for path in sorted(glob.glob(os.path.join(SRC, "*.json"))):
        name = os.path.splitext(os.path.basename(path))[0]
        subprocess.run([SPRITEGEN, path, "-o", os.path.join(OUT, name + ".png")], check=True)


if __name__ == "__main__":
    main()
