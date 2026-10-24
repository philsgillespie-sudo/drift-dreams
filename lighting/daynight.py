"""The game clock and the ambient light it gives. Pure logic: nothing here draws."""

DAY_SECONDS = 360            # real seconds per game day
NIGHT_START, NIGHT_END = 21.0, 5.0

# hour -> ambient light the drawn city is multiplied by; (255, 255, 255) leaves it untouched
SKY_KEYS = [
    (0.0, (35, 40, 85)),       # deep night, blue
    (5.0, (45, 45, 95)),
    (6.5, (255, 170, 140)),    # sunrise, pink
    (8.0, (255, 255, 255)),    # full day
    (17.0, (255, 255, 255)),
    (18.5, (255, 150, 90)),    # sunset, orange
    (19.5, (120, 80, 140)),    # dusk, purple
    (21.0, (35, 40, 85)),
    (24.0, (35, 40, 85)),
]


def smoothstep(t):
    return t * t * (3 - 2 * t)


def ambient_at(hour):
    """Ambient light for an hour of the day, eased between SKY_KEYS."""
    hour %= 24
    for (h0, c0), (h1, c1) in zip(SKY_KEYS, SKY_KEYS[1:]):
        if h0 <= hour <= h1:
            t = smoothstep((hour - h0) / (h1 - h0))
            return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
    return SKY_KEYS[-1][1]


class DayNightCycle:
    """A 24 hour clock running `day_seconds` real seconds per day."""

    def __init__(self, hour=17.0, day_seconds=DAY_SECONDS):
        self.hour = hour % 24
        self.day_seconds = day_seconds

    def update(self, dt, speed=1.0):
        self.hour = (self.hour + dt * speed * 24 / self.day_seconds) % 24

    def skip(self, hours):
        self.hour = (self.hour + hours) % 24

    @property
    def ambient(self):
        return ambient_at(self.hour)

    @property
    def darkness(self):
        """0 in full daylight, about 0.8 in the dead of night."""
        return 1 - sum(self.ambient) / (3 * 255)

    @property
    def is_night(self):
        return self.hour >= NIGHT_START or self.hour < NIGHT_END

    def label(self):
        return f"{int(self.hour):02d}:{int(self.hour % 1 * 60):02d}"
