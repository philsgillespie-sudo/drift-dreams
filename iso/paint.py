"""Paint ramps shared by the sprite generator and the game, so recoloured cars match exactly.

A body colour becomes five tones (deep shadow, shadow, base, light, specular) and a stripe
colour three (shadow, base, light). Shadows lean toward blue-purple, lights toward warm white.
"""


def _rgb(hex_col):
    h = hex_col.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def _mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def ramp(base):
    c = _rgb(base)
    return [_hex(_mix(c, (14, 10, 34), 0.62)), _hex(_mix(c, (26, 20, 60), 0.34)), _hex(c),
            _hex(_mix(c, (255, 244, 214), 0.3)), _hex(_mix(c, (255, 255, 246), 0.62))]


def stripe_ramp(base):
    c = _rgb(base)
    return [_hex(_mix(c, (40, 34, 70), 0.3)), _hex(c), _hex(_mix(c, (255, 255, 250), 0.45))]
