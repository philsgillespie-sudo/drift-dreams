"""Engine audio: an invented gearbox for the revs, and a crossfading loop ladder."""
import bisect
import math

IDLE_RPM = 700
SHIFT_RPM = 2800   # where the revs land after an upshift
REDLINE = 6200
GEAR_TOPS = [0, 90, 170, 250, 340, 450]  # road speed (units/s) each gear tops out at


def target_rpm(speed, throttle, sliding):
    """RPM the engine is heading for. The car has no gearbox, so one is made
    up from road speed; throttle revs it freely when stationary, and partly
    when the rear wheels are spinning in a slide."""
    gear = next((g for g in range(1, len(GEAR_TOPS)) if speed < GEAR_TOPS[g]), len(GEAR_TOPS) - 1)
    lo, hi = GEAR_TOPS[gear - 1], GEAR_TOPS[gear]
    frac = min(1.0, max(0.0, (speed - lo) / (hi - lo)))
    floor = IDLE_RPM if gear == 1 else SHIFT_RPM
    rpm = floor + (REDLINE - floor) * frac
    free = 0.85 if speed < 20 else 0.35 if sliding else 0.0
    rpm = max(rpm, IDLE_RPM + throttle * free * (REDLINE - IDLE_RPM))
    return min(REDLINE, rpm + 400 * throttle)


class EngineVoice:
    """One engine, built from loops recorded at fixed RPMs.

    pygame can't pitch-shift, so the two rungs either side of the current RPM
    play together and crossfade. Rungs alternate between the two channels, so
    whenever a channel switches loop it is the one that has faded to silence.
    """

    def __init__(self, channels, ladder):
        self.channels = channels
        self.ladder = ladder                # [(rpm, Sound)], low to high
        self.rpms = [rpm for rpm, _ in ladder]
        self.rungs = [None, None]           # rung playing on each channel

    def update(self, rpm, left, right):
        rpms = self.rpms
        rpm = min(max(rpm, rpms[0]), rpms[-1])
        i = min(bisect.bisect_right(rpms, rpm) - 1, len(rpms) - 2)
        f = math.log(rpm / rpms[i]) / math.log(rpms[i + 1] / rpms[i])
        for rung, mix in ((i, 1 - f), (i + 1, f)):
            k = rung % 2
            if self.rungs[k] != rung:
                self.channels[k].play(self.ladder[rung][1], loops=-1)
                self.rungs[k] = rung
            g = math.sqrt(mix)  # equal-power crossfade
            self.channels[k].set_volume(left * g, right * g)
