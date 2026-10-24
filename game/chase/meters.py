"""The two meters a pursuit is decided by. Each only measures; the rules decide what a full one means."""
from .. import config


class BustMeter:
    """Fills while the cop sits on the robber's bumper, fastest once the robber is boxed in and stopped;
    a hard ram adds a chunk. Drains while the robber is out of reach."""

    def __init__(self):
        self.value = 0.0          # 0..1

    @property
    def full(self):
        return self.value >= 1.0

    def update(self, dt, cop, robber):
        """cop, robber: their cars."""
        if cop.pos.distance_to(robber.pos) < config.BUST_RANGE:
            rate = 1.0 if robber.vel.length() < config.BUST_SLOW else config.BUST_MOVING
            self.value += rate * dt / config.BUST_TIME
        else:
            self.value -= config.BUST_DRAIN * dt
        self.value = max(0.0, min(1.0, self.value))

    def ram(self, impact):
        if impact > config.RAM_IMPACT:
            self.value = min(1.0, self.value + min(config.RAM_BUST_MAX, config.RAM_BUST * impact / config.RAM_IMPACT))


class GetawayMeter:
    """Fills while the robber is far from the cop; drains, quicker than it fills, once the cop is back in range."""

    def __init__(self):
        self.value = 0.0          # 0..1

    @property
    def full(self):
        return self.value >= 1.0

    def update(self, dt, cop, robber):
        step = dt / config.GETAWAY_TIME
        if cop.pos.distance_to(robber.pos) > config.GETAWAY_RANGE:
            self.value += step
        else:
            self.value -= step * config.GETAWAY_DRAIN
        self.value = max(0.0, min(1.0, self.value))
