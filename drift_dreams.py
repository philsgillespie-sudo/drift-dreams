"""Cops & Robbers: a two-player chase round an open isometric city, with arcade drift handling.

One player is the cop, the other the robber; the cop busts the robber by staying on their bumper
or ramming them, the robber wins by outlasting the clock or getting far enough away. Roles swap
every round; first to 3 rounds wins. One player alone gets a free drive.

Keyboard: arrows / WASD drive, SPACE handbrake (drift), T back onto the road,
R back to the start (free drive), ESC menu / quit, [ and ] move the clock an hour.
Gamepad: RT throttle, LT brake, left stick / d-pad steer, A or RB handbrake,
Y back onto the road, START drive / rematch, BACK menu. See input/ for the mappings.
Sprites are spritegen sheets in assets/sprites, built from sprites_src/ by tools/gen_sprites.py.
Run with --time HOUR to start at that time of day, --no-vsync to let frames run unpaced,
--players 2 to start with a second player in a window of their own (or press 2 in the menu): the chase needs two.

Layout: game/ is the game (session, systems, scenes, rendering), districts/ the map pieces that
world.py joins up, roads.py the road network the traffic drives, core/ engine helpers.
"""
import argparse
import sys

import pygame

from game import Game
from game.config import START_HOUR

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cops & Robbers")
    parser.add_argument("--time", type=float, default=START_HOUR, metavar="HOUR",
                        help="time of day to start at, 0-24 (default %(default)g)")
    parser.add_argument("--no-vsync", action="store_true", help="don't sync frames to the monitor")
    parser.add_argument("--players", type=int, choices=(1, 2), default=1,
                        help="2: a second player in their own window (on the second monitor if there is one)")
    args = parser.parse_args()
    Game(start_hour=args.time, vsync=not args.no_vsync, players=args.players).run()
    pygame.quit()
    sys.exit()
