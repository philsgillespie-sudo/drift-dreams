"""Drift Dreams: open-world drifting around an isometric city.

Drive anywhere and chain drifts, near misses and smashed street furniture into combos.

Keyboard: arrows / WASD drive, SPACE handbrake (drift), T back onto the road,
R back to the start, ESC menu / quit, [ and ] move the clock an hour.
Gamepad: RT throttle, LT brake, left stick / d-pad steer, A or RB handbrake,
Y back onto the road, START drive, BACK menu. See input/ for the mappings.
Sprites are spritegen sheets in assets/sprites, built from sprites_src/ by tools/gen_sprites.py.
Run with --time HOUR to start at that time of day.
"""
import argparse
import math
import os
import random
import sys

import pygame
from pygame.math import Vector2 as V

from car import CAR_RADIUS, Car
from district import T
from input import InputManager, actions
from iso import ZOOM, IsoCamera, IsoStack, blit_anchored, load_atlas, load_pivots, ramp, stack_slices, stripe_ramp
from lighting import CarLamps, DayNightCycle, LightingRenderer, LitScene, StreetLamps
from sound import SoundManager
from traffic import ParkedCar, Traffic
from world import World

ROOT = os.path.dirname(os.path.abspath(__file__))
SPRITES = os.path.join(ROOT, "assets", "sprites")
SFX = os.path.join(ROOT, "assets", "audio", "sfx")

SCREEN_W, SCREEN_H = 1280, 720  # the world is drawn at full resolution, ZOOM pixels per world unit
FPS = 60
SEA = (52, 110, 176)
SKID_LIMIT = 4000
START_HOUR = 17.0          # late afternoon, so the first drive rolls into dusk
MENU_TIME_SPEED = 10       # the title screen city spins through the day
NIGHT_BONUS = 1.2          # combo points banked at night
NIGHT_TRAFFIC = 0.55       # share of the traffic still out at night

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


def paint_map(body, stripe=None):
    """Colour swaps from the sheet's red paint to `body`; no stripe paints the stripes over."""
    new = ramp(body)
    pairs = list(zip(ramp(BASE_PAINT[0]), new))
    pairs += zip(stripe_ramp(BASE_PAINT[1]), stripe_ramp(stripe) if stripe else new[1:4])
    return [(pygame.Color(a), pygame.Color(b)) for a, b in pairs]


class Smoke:
    __slots__ = ("pos", "vel", "age", "life", "z")

    def __init__(self, pos, vel, life=0.9):
        self.pos, self.vel = V(pos), V(vel)
        self.age, self.life, self.z = 0.0, life, 0.0


class Drop:
    """A droplet from a burst hydrant."""
    __slots__ = ("pos", "vel", "z", "vz", "age")

    def __init__(self, pos, vel, vz):
        self.pos, self.vel, self.z, self.vz, self.age = V(pos), V(vel), 4.0, vz, 0.0


class Prop:
    def __init__(self, kind, pos):
        self.kind = kind
        self.home = V(pos)
        self.pos = V(pos)
        self.vel = V()
        self.angle = random.uniform(0, 360)
        self.spin = 0.0
        self.hit = False
        self.radius = {"cone": 5, "hydrant": 5, "bin": 6}[kind]


class Game:
    def __init__(self, start_hour=START_HOUR):
        SoundManager.pre_init()
        pygame.init()
        pygame.display.set_caption("Drift Dreams")
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        self.view = self.screen
        self.clock = pygame.time.Clock()
        mono = "consolas,menlo,monospace"
        self.font = pygame.font.SysFont(mono, 22, bold=True)
        self.font_small = pygame.font.SysFont(mono, 16, bold=True)
        self.font_mid = pygame.font.SysFont(mono, 40, bold=True)
        self.font_big = pygame.font.SysFont(mono, 92, bold=True)

        self._loading_screen("Loading sprites...")
        self.input = InputManager()
        self.sound = SoundManager(SFX)
        tiles, _ = load_atlas(SPRITES, "tiles")
        tiles.update(load_atlas(SPRITES, "bridge_tiles")[0])
        decos = {}
        for sheet in ("bridge_rails", "bridge_towers"):
            frames, pivots = load_atlas(SPRITES, sheet)[0], load_pivots(SPRITES, sheet)
            decos.update({k: (f, pivots[k]) for k, f in frames.items()})
        self.decos = decos
        buildings, _ = load_atlas(SPRITES, "buildings")
        car_f, _ = load_atlas(SPRITES, "car_stack")
        prop_f, _ = load_atlas(SPRITES, "props_stack")
        scen_f, _ = load_atlas(SPRITES, "scenery_stack")
        fx_f, fx_anims = load_atlas(SPRITES, "fx")
        self.smoke_frames = [fx_f[k] for k in fx_anims["smoke"]]

        self._loading_screen("Painting cars...")
        coupe = IsoStack(stack_slices(car_f, "coupe"), steps=72)
        self.player_stacks = {name: coupe.recolored(paint_map(*p)) for name, p in PLAYER_PAINTS.items()}
        traffic_stacks = [IsoStack(stack_slices(car_f, m), steps=72) for m in TRAFFIC_MODELS]
        traffic_stacks = [s.recolored(paint_map(p)) for s in traffic_stacks for p in TRAFFIC_PAINTS]
        self.prop_stacks = {k: IsoStack(stack_slices(prop_f, k), steps=24) for k in ("cone", "hydrant", "bin")}
        scenery = {k: IsoStack(stack_slices(scen_f, k), steps=4, shadow=k != "lamp")
                   for k in ("tree", "pine", "bush", "lamp")}
        self.scenery = scenery

        self._loading_screen("Building the city...")
        self.world = World(tiles, buildings, scenery, decos)
        self.traffic = Traffic(traffic_stacks, self.world.parked)
        self.props = [Prop(k, p) for k, p in self.world.prop_spots]
        self.camera = IsoCamera((SCREEN_W, SCREEN_H))
        self.daynight = DayNightCycle(start_hour)
        self.lighting = LightingRenderer((SCREEN_W, SCREEN_H), [StreetLamps(), CarLamps()])

        self.color_names = list(PLAYER_PAINTS)
        self.color_choice = 0
        self.player = Car(self.world.start, math.pi / 2, self.player_stacks["red"])
        self.camera.jump_to(self.player.pos)
        self.smoke, self.skids, self.drops, self.popups, self.sprays = [], [], [], [], []
        self.score = 0
        self.combo_pending = 0.0
        self.combo_mult = 1
        self.combo_chain = 0.0
        self.best_combo = 0
        self.was_drifting = False
        self.time = 0.0
        self.started = False
        self.state = "menu"
        self.menu_t = 0.0
        self.autopilot = None    # tests can drive the player with a function(game) -> DriveControls

    def _loading_screen(self, msg):
        self.screen.fill((24, 22, 34))
        t = self.font_mid.render(msg, True, (240, 220, 255))
        self.screen.blit(t, t.get_rect(center=(SCREEN_W / 2, SCREEN_H / 2)))
        pygame.display.flip()
        pygame.event.pump()

    # -- main loop -------------------------------------------------------------
    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000.0, 1 / 30)
            if not self.handle_events():
                return
            self.update(dt)
            self.draw()
            pygame.display.flip()

    def handle_events(self):
        pending = []
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return False
            pending += self.input.handle_event(e)
        pending += self.input.poll_actions()
        for action in pending:
            if not self.on_action(action):
                return False
        for notice in self.input.take_notices():
            self.popup(notice, (200, 200, 255))
        return True

    def on_action(self, action):
        """Returns False to quit."""
        if action in (actions.TIME_BACK, actions.TIME_FWD):
            self.daynight.skip(1 if action == actions.TIME_FWD else -1)
            return True
        if self.state == "menu":
            if action == actions.BACK:
                return False
            if action in (actions.LEFT, actions.RIGHT):
                step = -1 if action == actions.LEFT else 1
                self.color_choice = (self.color_choice + step) % len(self.color_names)
                self.player.stack = self.player_stacks[self.color_names[self.color_choice]]
                self.sound.play("ui_click")
            elif action in (actions.CONFIRM, actions.SELECT):
                self.sound.play("ui_confirm")
                self.state = "drive"
                self.started = True
            return True
        if action == actions.BACK:
            self.sound.play("ui_back")
            self.state = "menu"
        elif action == actions.RESET:
            self.to_road()
        elif action == actions.RESTART:
            self.sound.play("ui_confirm")
            self.place_player(self.world.start, math.pi / 2)
        return True

    def place_player(self, pos, heading):
        p = self.player
        p.pos, p.heading = V(pos), heading
        p.vel, p.angvel, p.drifting, p.prev_wheels = V(), 0.0, False, None
        self.camera.jump_to(p.pos)
        self.lose_combo(None)

    def to_road(self):
        pos, heading = self.world.nearest_road(self.player.pos)
        # face whichever way along the road is closer to where the car points
        if abs(math.remainder(heading - self.player.heading, math.tau)) > math.pi / 2:
            heading += math.pi
        self.place_player(pos, heading)

    # -- update ----------------------------------------------------------------
    def update(self, dt):
        self.time += dt
        p = self.player
        driving = self.state == "drive"
        self.daynight.update(dt, 1 if driving else MENU_TIME_SPEED)
        self.traffic.set_density(NIGHT_TRAFFIC if self.daynight.is_night else 1.0)
        self.sound.update(dt, p, self.traffic.cars, listening=driving)
        if driving:
            c = self.autopilot(self) if self.autopilot else self.input.drive()
            p.update(dt, c.throttle, c.brake, c.steer, c.handbrake)
        else:
            self.menu_t += dt
            p.update(dt, 0, 0, 0, True)
        self.traffic.update(dt, p, self.camera)
        self.collide()
        everyone = [p] + self.traffic.all()
        for car in everyone:
            car.surface = self.world.surface_at(car.pos)
            car.on_kerb = self.world.on_sidewalk(car.pos)
        self.car_effects(p)
        for car in self.traffic.cars:
            if car.drifting or car.dazed > 0:
                self.car_effects(car)
        self.update_props(dt)
        if driving:
            self.near_misses()
            self.update_combo(dt)
        self.update_particles(dt)
        for pop in self.popups:
            pop[2] += dt
        self.popups = [pop for pop in self.popups if pop[2] < 1.8]
        self.camera.update(dt)
        if driving:
            self.camera.follow(p.pos, p.vel, dt)
        else:
            a = self.menu_t * 0.15
            self.camera.pan(p.pos + V(math.cos(a), math.sin(a)) * 160, dt)

    def collide(self):
        p = self.player
        cars = [p] + self.traffic.cars + self.traffic.parked
        for car in cars:
            if isinstance(car, ParkedCar) and car.vel.length_squared() < 1:
                continue
            res = self.world.collide(car.pos, CAR_RADIUS)
            if res is None:
                continue
            corr, n, kind = res
            car.pos += corr
            vn = car.vel.dot(n)
            if vn < 0:
                car.vel -= n * vn * 1.4
                car.vel *= 0.8
                car.angvel += random.uniform(-1, 1) * min(2.0, -vn / 150)
                if car is p and -vn > 60:
                    heavy = -vn > 170
                    self.sound.play("crash_heavy" if heavy else "crash_light", min(1.0, -vn / 300))
                    if heavy:
                        self.crash()
                    else:
                        self.camera.add_shake(3)
        # car against car (cheap box test first)
        for i in range(len(cars)):
            a = cars[i]
            for j in range(i + 1, len(cars)):
                b = cars[j]
                if abs(a.pos.x - b.pos.x) > 2 * CAR_RADIUS or abs(a.pos.y - b.pos.y) > 2 * CAR_RADIUS:
                    continue
                d = b.pos - a.pos
                dist = d.length()
                if not 0 < dist < CAR_RADIUS * 2:
                    continue
                n = d / dist
                push = (CAR_RADIUS * 2 - dist) / 2
                a.pos -= n * push
                b.pos += n * push
                rel = (b.vel - a.vel).dot(n)
                if rel < 0:
                    imp = n * rel * 0.75
                    a.vel += imp
                    b.vel -= imp
                    for c in (a, b):
                        c.angvel += random.uniform(-1, 1) * min(2.0, -rel / 100)
                        if c is not p and hasattr(c, "dazed") and -rel > 80:
                            c.dazed = 1.6
                    if p in (a, b):
                        other = b if a is p else a
                        other.near_miss_t = 3.0   # a hit is not a near miss
                        if -rel > 120:
                            self.sound.play("crash_heavy" if -rel > 280 else "crash_light", pos=other.pos)
                            self.camera.add_shake(5)
                            self.input.rumble(0.5, 150)
                            if -rel > 280:
                                self.crash()
                    elif -rel > 120:
                        self.sound.play("crash_light", 0.6, pos=a.pos)

    def crash(self):
        self.camera.add_shake(8)
        self.input.rumble(1.0, 250)
        self.lose_combo("CRASHED - COMBO LOST")

    def lose_combo(self, msg):
        if msg and self.combo_pending > 0:
            self.popup(msg, (255, 90, 90))
        self.combo_pending = 0.0
        self.combo_mult = 1
        self.combo_chain = 0.0

    def add_combo(self, pts, msg=None, color=(120, 220, 255)):
        self.combo_pending += pts
        self.combo_chain = max(self.combo_chain, 1.4)
        if msg:
            self.popup(msg, color)

    def car_effects(self, car):
        speed = car.vel.length()
        sliding = (car.drifting and speed > 60) or (abs(car.slip) > 0.2 and speed > 100)
        wheels = car.rear_wheels()
        if sliding and car.prev_wheels:
            col = (34, 34, 40) if car.surface == "road" else (70, 100, 45) if car.surface == "grass" else (150, 120, 80)
            for a, b in zip(car.prev_wheels, wheels):
                self.skids.append((V(a), V(b), col))
            if len(self.skids) > SKID_LIMIT:
                del self.skids[:400]
        car.prev_wheels = wheels if sliding else None
        if sliding and len(self.smoke) < 300 and random.random() < 0.6:
            if car.surface == "road" or random.random() < 0.3:
                w = random.choice(wheels)
                self.smoke.append(Smoke(w, car.vel * 0.15 + V(random.uniform(-15, 15), random.uniform(-15, 15))))

    def update_props(self, dt):
        p = self.player
        movers = [p] + self.traffic.cars
        for prop in self.props:
            if abs(prop.pos.x - p.pos.x) > 900 or abs(prop.pos.y - p.pos.y) > 900:
                continue
            for car in movers:
                d = prop.pos - car.pos
                dist = d.length()
                lim = CAR_RADIUS + prop.radius
                if 0 < dist < lim:
                    n = d / dist
                    prop.pos = car.pos + n * lim
                    prop.vel = car.vel * 1.1 + n * 80
                    prop.spin = random.uniform(-720, 720)
                    speed = car.vel.length()
                    if speed > 30:
                        self.sound.play("cone_hit", min(1.0, speed / 200), pos=prop.pos)
                    car.vel *= 0.97 if prop.kind == "cone" else 0.85
                    if car is p and not prop.hit and speed > 60 and self.state == "drive":
                        prop.hit = True
                        pts = {"cone": 40, "bin": 60, "hydrant": 120}[prop.kind]
                        self.add_combo(pts, f"+{pts} SMASH", (255, 180, 90))
                        if prop.kind == "hydrant":
                            self.sprays.append([V(prop.home), 6.0])
            if prop.vel.length_squared() > 1:
                prop.pos += prop.vel * dt
                prop.vel *= math.exp(-2.5 * dt)
                prop.angle += prop.spin * dt
                prop.spin *= math.exp(-2.5 * dt)
                res = self.world.collide(prop.pos, prop.radius)
                if res:
                    prop.pos += res[0]
                    prop.vel = prop.vel.reflect(res[1]) * 0.5

    def near_misses(self):
        p = self.player
        speed = p.vel.length()
        if speed < 200:
            return
        for car in self.traffic.cars:
            if car.near_miss_t > 0:
                continue
            d = car.pos.distance_to(p.pos)
            if 2 * CAR_RADIUS < d < 2 * CAR_RADIUS + 14:
                car.near_miss_t = 3.0
                self.add_combo(150, "+150 NEAR MISS")

    def update_combo(self, dt):
        p = self.player
        speed = p.vel.length()
        drifting = p.drifting and speed > 100 and abs(p.slip) > 0.15
        if drifting and p.surface != "road":
            self.lose_combo("OFF ROAD - COMBO LOST")
            drifting = False
        if drifting:
            if not self.was_drifting and self.combo_chain > 0:
                self.combo_mult = min(8, self.combo_mult + 1)
            self.combo_pending += abs(math.degrees(p.slip)) * speed * 0.08 * dt
            self.combo_chain = 1.4
        elif self.combo_chain > 0:
            self.combo_chain -= dt
            if self.combo_chain <= 0 and self.combo_pending > 0:
                night = self.daynight.is_night
                pts = int(self.combo_pending * self.combo_mult * (NIGHT_BONUS if night else 1))
                self.score += pts
                self.best_combo = max(self.best_combo, pts)
                self.popup(f"+{pts}" + (f"  x{self.combo_mult}" if self.combo_mult > 1 else "")
                           + ("  NIGHT" if night else ""), (120, 255, 140))
                self.combo_pending = 0.0
                self.combo_mult = 1
        self.was_drifting = drifting

    def update_particles(self, dt):
        for s in self.smoke:
            s.age += dt
            s.pos += s.vel * dt
            s.vel *= math.exp(-1.5 * dt)
            s.z += 8 * dt
        self.smoke = [s for s in self.smoke if s.age < s.life]
        for spray in self.sprays:
            spray[1] -= dt
            for _ in range(3):
                a = random.uniform(0, math.tau)
                self.drops.append(Drop(spray[0], V(math.cos(a), math.sin(a)) * random.uniform(5, 25),
                                       random.uniform(60, 110)))
        self.sprays = [s for s in self.sprays if s[1] > 0]
        for d in self.drops:
            d.age += dt
            d.pos += d.vel * dt
            d.vz -= 220 * dt
            d.z += d.vz * dt
        self.drops = [d for d in self.drops if d.z > 0 and d.age < 2]

    def popup(self, text, color):
        self.popups.append([text, color, 0.0])

    # -- drawing -----------------------------------------------------------------
    def draw(self):
        view, cam = self.view, self.camera
        view.fill(SEA)
        cam.begin()
        self.world.draw_ground(view, cam)
        self.draw_skids(view, cam)
        things = self.visible_things(cam)
        buildings = self.draw_things(view, cam, things)
        dn = self.daynight
        self.lighting.draw(view, cam, self.lit_scene(things), dn.ambient, dn.darkness,
                           lambda light, s: self.covered(s, light.pos.x + light.pos.y, buildings))

        if self.state == "menu":
            self.draw_menu()
        else:
            self.draw_hud()

    def draw_skids(self, view, cam):
        vr = view.get_rect().inflate(40, 40)
        for a, b, col in self.skids:
            sa = cam.to_screen(a)
            if vr.collidepoint(sa):
                pygame.draw.line(view, col, sa, cam.to_screen(b), 2 * ZOOM - 1)

    def visible_things(self, cam):
        """Everything on screen that stands up, in draw order: (depth, tiebreak, kind, payload)."""
        world, p = self.world, self.player
        things = []
        for obj in world.visible_objects(cam.view, extra_top=320 * ZOOM):
            if obj[0] == "building":
                _, i, j = obj
                things.append(((i + j + 1) * T, 0, "building", (i, j)))
            elif obj[0] == "deco":
                _, name, depth, rect = obj
                things.append((depth, 0, "deco", (name, rect)))
            else:
                _, kind, pos, ang = obj
                if cam.visible(pos, 40):
                    things.append((pos.x + pos.y, 1, "static", (kind, pos, ang)))
        for prop in self.props:
            if cam.visible(prop.pos, 20):
                things.append((prop.pos.x + prop.pos.y, 2, "prop", prop))
        for car in [p] + self.traffic.all():
            if cam.visible(car.pos, 40):
                things.append((car.pos.x + car.pos.y, 3, "car", car))
        for s in self.smoke:
            if cam.visible(s.pos, 20):
                things.append((s.pos.x + s.pos.y + 6, 5, "smoke", s))
        things.sort(key=lambda t: (t[0], t[1]))
        return things

    @staticmethod
    def lit_scene(things):
        """The lamps and driving cars among the visible things, for the lighting."""
        scene = LitScene()
        for _, _, kind, obj in things:
            if kind == "static" and obj[0] == "lamp":
                scene.lamps.append((obj[1], obj[2]))
            elif kind == "car" and not isinstance(obj, ParkedCar):
                scene.cars.append(obj)
        return scene

    @staticmethod
    def covered(point, depth, buildings):
        """Whether a building standing in front of `depth` has a solid pixel at screen `point`
        (see-through faded buildings don't count)."""
        for b_depth, rect, surf in buildings:
            if b_depth > depth and rect.collidepoint(point):
                if surf.get_at((int(point[0]) - rect.x, int(point[1]) - rect.y)).a > 200:
                    return True
        return False

    def draw_things(self, view, cam, things):
        """Draws the things and returns the buildings drawn, as (depth, screen rect, image)."""
        world, p = self.world, self.player
        p_img = p.image()
        p_screen = cam.to_screen(p.pos)
        p_rect = p_img[0].get_rect(topleft=(p_screen.x - p_img[1][0], p_screen.y - p_img[1][1]))
        p_rect.inflate_ip(8 * ZOOM, 8 * ZOOM)
        p_depth = p.pos.x + p.pos.y

        # buildings standing between the camera and the player are drawn see-through, whole lot at once
        rects = {}
        hiding = set()
        for depth, _, kind, obj in things:
            if kind == "building":
                i, j = obj
                s = cam.to_screen((i * T, j * T))
                gy = world.building_image(i, j)[1]
                rect = rects[obj] = pygame.Rect(s.x - 32 * ZOOM, s.y - gy, 64 * ZOOM, gy + 32 * ZOOM)
                if depth > p_depth + 8 and rect.colliderect(p_rect):
                    hiding.add(world.buildings[obj][0])

        world.draw_cables(view, cam, "back")
        screen_rect = view.get_rect()
        drawn = []
        for depth, _, kind, obj in things:
            if kind == "building":
                rect = rects[obj]
                if rect.colliderect(screen_rect):
                    faded = world.buildings[obj][0] in hiding
                    img = world.building_image(*obj, faded=faded)[0]
                    view.blit(img, rect)
                    drawn.append((depth, rect, img))
            elif kind == "deco":
                name, rect = obj
                view.blit(self.decos[name][0], (rect.x - cam.ox, rect.y - cam.oy))
            elif kind == "static":
                k, pos, ang = obj
                blit_anchored(view, self.scenery[k].image(ang), cam.to_screen(pos))
            elif kind == "prop":
                blit_anchored(view, self.prop_stacks[obj.kind].image(obj.angle), cam.to_screen(obj.pos))
            elif kind == "car":
                blit_anchored(view, obj.image(), cam.to_screen(obj.pos))
            else:
                t = obj.age / obj.life
                img = self.smoke_frames[min(3, int(t * 4))]
                img.set_alpha(int(200 * (1 - t)))
                s = cam.to_screen(obj.pos, obj.z)
                view.blit(img, img.get_rect(center=(s.x, s.y - 4 * ZOOM)))
        for d in self.drops:
            s = cam.to_screen(d.pos, d.z)
            view.fill((150, 210, 255), (s.x, s.y, ZOOM + 1, ZOOM + 1))
            view.fill((230, 246, 255), (s.x, s.y, 1, 1))
        world.draw_cables(view, cam, "front")
        if hiding:
            # x-ray: a faint copy of the car on top so it never vanishes behind a tower
            ghost = p_img[0].copy()
            ghost.set_alpha(110)
            blit_anchored(view, (ghost, p_img[1]), p_screen)
        return drawn

    def text(self, s, font, color, pos, anchor="topleft", shadow=True):
        img = font.render(s, True, color)
        rect = img.get_rect(**{anchor: pos})
        if shadow:
            self.screen.blit(font.render(s, True, (0, 0, 0)), rect.move(2, 2))
        self.screen.blit(img, rect)
        return rect

    def draw_hud(self):
        scr = self.screen
        p = self.player
        panel = pygame.Surface((260, 104), pygame.SRCALPHA)
        panel.fill((10, 0, 30, 130))
        scr.blit(panel, (12, 12))
        self.text(f"SCORE {self.score}", self.font, (255, 255, 255), (24, 20))
        self.text(f"BEST COMBO {self.best_combo}", self.font_small, (200, 200, 230), (24, 54))
        self.draw_clock((24, 82))

        mm = self.world.minimap
        mx, my = SCREEN_W - mm.get_width() - 12, 12
        scr.blit(mm, (mx, my))
        for car in self.traffic.cars:
            q = self.world.minimap_pos(car.pos) + V(mx, my)
            scr.fill((230, 230, 240), (q.x, q.y, 2, 2))
        q = self.world.minimap_pos(p.pos) + V(mx, my)
        pygame.draw.circle(scr, (0, 0, 0), q, 5)
        pygame.draw.circle(scr, (255, 80, 160), q, 4)

        kmh = int(p.vel.length() * 0.6)
        self.text(f"{kmh:3d}", self.font_mid, (255, 255, 255), (24, SCREEN_H - 92))
        self.text("km/h", self.font_small, (200, 200, 220), (110, SCREEN_H - 76))

        if self.combo_pending > 0:
            s = f"{int(self.combo_pending)}"
            if self.combo_mult > 1:
                s += f"  x{self.combo_mult}"
            self.text(s, self.font_mid, (255, 255, 160), (SCREEN_W / 2, 18), "midtop")
            w = int(160 * max(0.0, min(1.0, self.combo_chain / 1.4)))
            pygame.draw.rect(scr, (255, 255, 160), (SCREEN_W / 2 - 80, 66, w, 4))

        for k, (txt, col, age) in enumerate(self.popups[-4:]):
            y = SCREEN_H * 0.3 - age * 30 + k * 32
            self.text(txt, self.font, col, (SCREEN_W / 2, y), "center")

        if self.time < 8 and self.started:
            hint = ("RT gas  LT brake  A/RB drift  Y to road" if self.input.has_gamepad else
                    "ARROWS/WASD drive  SPACE drift  T to road  R start")
            self.text(hint, self.font_small, (240, 240, 240), (SCREEN_W / 2, SCREEN_H - 30), "center")

    def draw_clock(self, pos):
        """Time of day with a sun or moon, and the night bonus while it's on."""
        scr, dn = self.screen, self.daynight
        c = (pos[0] + 8, pos[1] + 9)
        if dn.is_night:
            pygame.draw.circle(scr, (235, 235, 255), c, 7)
            pygame.draw.circle(scr, (10, 0, 30), (c[0] + 4, c[1] - 2), 6)   # bite out a crescent
        else:
            pygame.draw.circle(scr, (255, 214, 60), c, 6)
            for k in range(8):
                a = k * math.pi / 4
                pygame.draw.line(scr, (255, 214, 60), (c[0] + math.cos(a) * 8, c[1] + math.sin(a) * 8),
                                 (c[0] + math.cos(a) * 10, c[1] + math.sin(a) * 10), 2)
        self.text(dn.label(), self.font_small, (230, 230, 250), (pos[0] + 24, pos[1]))
        if dn.is_night:
            self.text(f"NIGHT x{NIGHT_BONUS:g}", self.font_small, (170, 200, 255), (pos[0] + 100, pos[1]))

    def draw_menu(self):
        scr = self.screen
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((20, 0, 40, 120))
        scr.blit(shade, (0, 0))
        title = "DRIFT DREAMS"
        for k, col in enumerate(((255, 90, 170), (90, 220, 255))):
            self.text(title, self.font_big, col, (SCREEN_W / 2 + (k * 2 - 1) * 3, 130), "center", shadow=False)
        self.text(title, self.font_big, (255, 245, 255), (SCREEN_W / 2, 130), "center", shadow=False)
        self.text("an open-world drift through the city", self.font, (230, 220, 255), (SCREEN_W / 2, 200), "center")

        band = pygame.Surface((SCREEN_W, 170), pygame.SRCALPHA)
        band.fill((20, 0, 40, 140))
        scr.blit(band, (0, 245))
        n = len(self.color_names)
        for k, name in enumerate(self.color_names):
            x = SCREEN_W / 2 + (k - (n - 1) / 2) * 140
            img = self.player_stacks[name].image(self.menu_t * 60 + k * 30)
            surf, (ax, ay) = img
            mag = 3 / ZOOM   # the sprites already carry ZOOM pixels per world unit
            big = pygame.transform.smoothscale(surf, (round(surf.get_width() * mag), round(surf.get_height() * mag)))
            if k == self.color_choice:
                pygame.draw.rect(scr, (255, 214, 60), pygame.Rect(x - 62, 262, 124, 120), 3, 10)
            scr.blit(big, (x - ax * mag, 336 - ay * mag))
        self.text(self.color_names[self.color_choice].upper(), self.font, (255, 214, 60),
                  (SCREEN_W / 2, 400), "center")
        verb = "drive" if not self.started else "keep driving"
        if self.input.gamepad_name:
            self.text(f"LEFT/RIGHT paint   A/START {verb}   BACK quit", self.font, (240, 240, 240),
                      (SCREEN_W / 2, 470), "center")
            self.text(f"Controller: {self.input.gamepad_name}", self.font_small, (170, 200, 255),
                      (SCREEN_W / 2, 610), "center")
        else:
            self.text(f"LEFT/RIGHT paint   ENTER {verb}   ESC quit", self.font, (240, 240, 240),
                      (SCREEN_W / 2, 470), "center")
        self.text("Hold handbrake while turning to drift. Drifts, near misses and smashes chain into combos.",
                  self.font_small, (220, 210, 240), (SCREEN_W / 2, 530), "center")
        self.text("Crashing or drifting off the tarmac loses the combo.",
                  self.font_small, (220, 210, 240), (SCREEN_W / 2, 556), "center")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Drift Dreams")
    parser.add_argument("--time", type=float, default=START_HOUR, metavar="HOUR",
                        help="time of day to start at, 0-24 (default %(default)g)")
    Game(start_hour=parser.parse_args().time).run()
    pygame.quit()
    sys.exit()
