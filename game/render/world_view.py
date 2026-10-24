"""Draws the world: ground, then everything standing depth-sorted back to front, then the lighting.

Each frame, item sources list what is on screen as (depth, tiebreak, kind, payload) and a drawer
per kind draws it. A new kind of thing on the map is one source and one drawer.
"""
from operator import itemgetter

from iso import ZOOM, blit_anchored
from lighting import LitScene, Sirens

from .. import config

SCENERY_TALLEST = 64 * ZOOM     # how far above its ground a tree or lamp can reach
FADED_ALPHA = 96                # buildings between the camera and the view's player
GHOST_ALPHA = 110               # that player drawn over them, so it never vanishes
LIGHTBAR = ((255, 60, 60), (70, 120, 255))   # lit lamp colours, red then blue
LIGHTBAR_OFF = ((90, 20, 24), (24, 36, 90))
_ORDER = itemgetter(0, 1)


class WorldRenderer:
    def __init__(self, assets, world, session, lighting):
        self.world, self.session, self.lighting = world, session, lighting
        self.decos = assets.decos
        self.scenery = assets.scenery
        self.prop_stacks = assets.prop_stacks
        self.smoke_frames = assets.smoke_frames
        self.sources = [self._world_items, self._prop_items, self._car_items, self._smoke_items]
        self.drawers = {
            "building": self._draw_building,
            "deco": self._draw_deco,
            "static": self._draw_static,
            "prop": self._draw_prop,
            "car": self._draw_car,
            "smoke": self._draw_smoke,
        }

    def draw(self, view, cam, focus):
        """focus: the car this view follows (buildings in front of it turn see-through)."""
        view.fill(config.SEA)
        cam.begin()
        self.world.draw_ground(view, cam)
        things = self.visible_things(cam)
        buildings = self.draw_things(view, cam, things, focus)
        dn = self.session.daynight
        covered = self.covered
        self.lighting.draw(view, cam, self.lit_scene(things, self.session.time), dn.ambient, dn.darkness,
                           lambda light, s: covered(s, light.pos.x + light.pos.y, buildings))

    # -- what's on screen --------------------------------------------------------
    def visible_things(self, cam):
        """Everything on screen that stands up, in draw order: (depth, tiebreak, kind, payload)."""
        things = []
        for source in self.sources:
            source(cam, things)
        things.sort(key=_ORDER)
        return things

    def _world_items(self, cam, out):
        visible = cam.visible
        for obj in self.world.visible_objects(cam.view, extra_top=SCENERY_TALLEST):
            kind = obj[0]
            if kind == "building":
                block = obj[1]
                out.append((block.depth, 0, "building", block))
            elif kind == "deco":
                _, name, depth, rect = obj
                out.append((depth, 0, "deco", (name, rect)))
            else:
                _, k, pos, ang = obj
                if visible(pos, 40):
                    out.append((pos.x + pos.y, 1, "static", (k, pos, ang)))

    def _prop_items(self, cam, out):
        visible = cam.visible
        out += [(p.pos.x + p.pos.y, 2, "prop", p) for p in self.session.props.props if visible(p.pos, 20)]

    def _car_items(self, cam, out):
        visible = cam.visible
        out += [(c.pos.x + c.pos.y, 3, "car", c) for c in self.session.cars() if visible(c.pos, 40)]

    def _smoke_items(self, cam, out):
        visible = cam.visible
        out += [(s.pos.x + s.pos.y + 6, 5, "smoke", s) for s in self.session.particles.smoke if visible(s.pos, 20)]

    @staticmethod
    def lit_scene(things, time):
        """The lamps and driving cars among the visible things, for the lighting."""
        scene = LitScene(time=time)
        for _, _, kind, obj in things:
            if kind == "static" and obj[0] == "lamp":
                scene.lamps.append((obj[1], obj[2]))
            elif kind == "car" and not obj.parked:
                scene.cars.append(obj)
        return scene

    @staticmethod
    def covered(point, depth, buildings):
        """Whether a building standing in front of `depth` has a solid pixel at screen `point`
        (see-through faded buildings aren't listed, so they don't count)."""
        x, y = int(point[0]), int(point[1])
        for b_depth, rect, surf in buildings:
            if b_depth > depth and rect.collidepoint(x, y):
                if surf.get_at((x - rect.x, y - rect.y)).a > 200:
                    return True
        return False

    # -- drawing -------------------------------------------------------------------
    def draw_things(self, view, cam, things, p):
        """Draws the things and returns the solid buildings drawn, as (depth, screen rect, image).
        p: the car the view follows."""
        p_img = p.image()
        p_screen = cam.to_screen(p.pos)
        p_rect = p_img[0].get_rect(topleft=(p_screen.x - p_img[1][0], p_screen.y - p_img[1][1]))
        p_rect.inflate_ip(8 * ZOOM, 8 * ZOOM)
        p_depth = p.pos.x + p.pos.y

        # buildings standing between the camera and the car are drawn see-through, whole lot at once
        ox, oy = -cam.ox, -cam.oy
        hiding = set()
        for depth, _, kind, obj in things:
            if kind == "building" and depth > p_depth + 8 and obj.rect.move(ox, oy).colliderect(p_rect):
                hiding.add(obj.lot)

        self.world.draw_cables(view, cam, "back")
        frame = _Frame(view, cam, view.get_rect(), hiding, self.session.time)
        drawers = self.drawers
        for thing in things:
            drawers[thing[2]](frame, thing)
        for d in self.session.particles.drops:
            s = cam.to_screen(d.pos, d.z)
            view.fill((150, 210, 255), (s.x, s.y, ZOOM + 1, ZOOM + 1))
            view.fill((230, 246, 255), (s.x, s.y, 1, 1))
        self.world.draw_cables(view, cam, "front")
        if hiding:
            # x-ray: a faint copy of the car on top so it never vanishes behind a tower
            surf = p_img[0]
            surf.set_alpha(GHOST_ALPHA)
            blit_anchored(view, p_img, p_screen)
            surf.set_alpha(255)
        return frame.buildings

    @staticmethod
    def _draw_building(frame, thing):
        depth, _, _, block = thing
        rect = block.rect.move(-frame.cam.ox, -frame.cam.oy)
        if not rect.colliderect(frame.screen_rect):
            return
        img = block.image()
        if block.lot in frame.hiding:
            img.set_alpha(FADED_ALPHA)
            frame.view.blit(img, rect)
            img.set_alpha(255)
        else:
            frame.view.blit(img, rect)
            frame.buildings.append((depth, rect, img))

    def _draw_deco(self, frame, thing):
        name, rect = thing[3]
        frame.view.blit(self.decos[name][0], (rect.x - frame.cam.ox, rect.y - frame.cam.oy))

    def _draw_static(self, frame, thing):
        k, pos, ang = thing[3]
        blit_anchored(frame.view, self.scenery[k].image(ang), frame.cam.to_screen(pos))

    def _draw_prop(self, frame, thing):
        prop = thing[3]
        blit_anchored(frame.view, self.prop_stacks[prop.kind].image(prop.angle), frame.cam.to_screen(prop.pos))

    @staticmethod
    def _draw_car(frame, thing):
        car = thing[3]
        blit_anchored(frame.view, car.image(), frame.cam.to_screen(car.pos))
        if car.siren:
            lit = Sirens.lit_side(frame.time)
            for side, lamp in enumerate(Sirens.lamps(car)):
                s = frame.cam.to_screen(lamp, Sirens.BAR_Z)
                color = LIGHTBAR[side] if side == lit else LIGHTBAR_OFF[side]
                frame.view.fill(color, (s.x - ZOOM, s.y - ZOOM, 2 * ZOOM, 2 * ZOOM))

    def _draw_smoke(self, frame, thing):
        s = thing[3]
        t = s.age / s.life
        img = self.smoke_frames[min(3, int(t * 4))]
        img.set_alpha(int(200 * (1 - t)))
        p = frame.cam.to_screen(s.pos, s.z)
        frame.view.blit(img, img.get_rect(center=(p.x, p.y - 4 * ZOOM)))


class _Frame:
    """What the drawers share while drawing one frame."""
    __slots__ = ("view", "cam", "screen_rect", "hiding", "buildings", "time")

    def __init__(self, view, cam, screen_rect, hiding, time):
        self.view, self.cam, self.screen_rect, self.hiding, self.time = view, cam, screen_rect, hiding, time
        self.buildings = []
