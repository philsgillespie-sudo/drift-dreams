"""Headless frame-time profile: drives the player round the city and reports how long frames take.

    py tools/frame_profile.py [--frames N] [--hour H] [--cprofile]

Runs with SDL's dummy video and audio drivers, so no window opens. Frame time is update + draw
(the event pump is timed apart: SDL device handling can stall it). The player is put back on the
road every 400 frames; those teleport frames bake a screenful of ground and are left out of "max".
--cprofile also prints the 30 costliest calls.
"""
import argparse
import cProfile
import os
import pstats
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("SDL_VIDEO_DRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from game import Game  # noqa: E402
from input import DriveControls  # noqa: E402

TELEPORT_EVERY = 400
BUDGET = 1000 / 60


def pilot(game):
    """Full throttle, swinging into handbrake drifts every few seconds."""
    t = game.time
    return DriveControls(throttle=1.0, steer=1.0 if int(t / 3) % 3 == 0 else 0.0, handbrake=int(t * 2) % 5 == 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--frames", type=int, default=1500)
    ap.add_argument("--hour", type=float, default=20.0, help="time of day; night adds the lighting pass")
    ap.add_argument("--cprofile", action="store_true")
    args = ap.parse_args()

    t0 = time.perf_counter()
    g = Game(start_hour=args.hour)
    print(f"startup {time.perf_counter() - t0:.2f}s")
    g.change_scene("drive")
    g.started = True
    g.autopilot = pilot

    prof = cProfile.Profile() if args.cprofile else None
    frames, updates, draws, pumps = [], [], [], []
    steady = []
    if prof:
        prof.enable()
    for f in range(args.frames):
        a = time.perf_counter()
        pygame.event.pump()
        b = time.perf_counter()
        g.update(1 / 60)
        c = time.perf_counter()
        g.draw()
        d = time.perf_counter()
        pumps.append((b - a) * 1000)
        updates.append((c - b) * 1000)
        draws.append((d - c) * 1000)
        frames.append((d - b) * 1000)
        if f % TELEPORT_EVERY > 2:
            steady.append(frames[-1])
        if f % TELEPORT_EVERY == TELEPORT_EVERY - 1:
            g.session.to_road()
    if prof:
        prof.disable()

    s, n = sorted(frames), len(frames)
    print(f"frames {n}: mean {sum(s) / n:.2f}ms  p50 {s[n // 2]:.2f}  p95 {s[int(n * .95)]:.2f}  "
          f"p99 {s[int(n * .99)]:.2f}  max (steady) {max(steady):.2f}  max (any) {s[-1]:.2f}")
    print(f"update mean {sum(updates) / n:.2f}ms   draw mean {sum(draws) / n:.2f}ms   "
          f"over budget: {sum(t > BUDGET for t in frames)}   slowest event pump {max(pumps):.1f}ms")
    if prof:
        pstats.Stats(prof).sort_stats("cumulative").print_stats(30)


if __name__ == "__main__":
    main()
