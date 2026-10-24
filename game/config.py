"""Game-wide settings: window, pacing, paints and the chase rules' tunables."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPRITES = os.path.join(ROOT, "assets", "sprites")
SFX = os.path.join(ROOT, "assets", "audio", "sfx")

SCREEN_W, SCREEN_H = 1280, 720  # the world is drawn at full resolution, ZOOM pixels per world unit
FPS = 60                   # frame cap without vsync
MAX_FPS = 240              # frame cap with vsync (in case the driver ignores it)
MAX_DT = 1 / 30            # longest step the simulation takes, however long a frame was
SEA = (52, 110, 176)
START_HOUR = 17.0          # late afternoon, so the first drive rolls into dusk
MENU_TIME_SPEED = 10       # the title screen city spins through the day
NIGHT_TRAFFIC = 0.55       # share of the traffic still out at night
TRAFFIC_COUNT = 28

# car paint: body, stripe (the sprites are painted red with white stripes; see iso.paint)
BASE_PAINT = ("#d8343c", "#f4f0e8")
PLAYER_PAINTS = {
    "red": BASE_PAINT,
    "blue": ("#3466d8", "#f4f0e8"),
    "yellow": ("#f2b630", "#2a2630"),
    "green": ("#38b45a", "#f4f0e8"),
    "purple": ("#9a4ae0", "#ffd23c"),
    "pink": ("#f06aa8", "#ffffff"),
}
POLICE_PAINT = ("#1c2234", "#f4f0e8")   # the cop's car, whatever paint they picked
TRAFFIC_PAINTS = ["#e6e8ee", "#9ea4ae", "#2c2e36", "#f0c419", "#2e4a8e", "#8e2c38", "#2e8e8a", "#c8b48c"]
TRAFFIC_MODELS = ("sedan", "hatch")
SCENERY = ("tree", "pine", "bush", "lamp")

# -- the chase -----------------------------------------------------------------
COP, ROBBER = "cop", "robber"
ROLE_COLORS = {COP: (90, 160, 255), ROBBER: (255, 150, 60)}
MATCH_WINS = 3             # rounds to win the match; roles swap every round
ROUND_TIME = 90.0          # the robber gets away if they're still free when it runs out
HEAD_START = 3             # seconds the cop is held at the start of a round
START_GAP = 120            # how far behind the robber the cop starts
RESULT_TIME = 4.0          # how long a round's result shows before the next one
REMATCH_DELAY = 1.5        # the match result shows at least this long before a rematch can start
BUST_RANGE = 56            # the cop this close fills the bust meter...
BUST_TIME = 2.0            # ...full in this long while the robber is (nearly) stopped
BUST_SLOW = 90             # robber speed under which they count as stopped
BUST_MOVING = 0.35         # share of the fill rate while the robber is still moving
BUST_DRAIN = 0.4           # meter lost per second out of range
RAM_IMPACT = 100           # the cop hitting the robber harder than this...
RAM_BUST = 0.2             # ...adds this much to the meter per RAM_IMPACT of closing speed
RAM_BUST_MAX = 0.45
GETAWAY_RANGE = 600        # the robber this far from the cop fills the getaway meter...
GETAWAY_TIME = 8.0         # ...and gets away once it's been full for this long in all
GETAWAY_DRAIN = 2.0        # meter lost per second (as a share of the fill rate) back in range
