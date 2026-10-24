"""Game-wide settings: window, pacing, paints and the scoring rules' tunables."""
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
NIGHT_BONUS = 1.2          # combo points banked at night
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
TRAFFIC_PAINTS = ["#e6e8ee", "#9ea4ae", "#2c2e36", "#f0c419", "#2e4a8e", "#8e2c38", "#2e8e8a", "#c8b48c"]
TRAFFIC_MODELS = ("sedan", "hatch")
SCENERY = ("tree", "pine", "bush", "lamp")
