"""Light map: darkens the drawn scene to the ambient light and adds the lights back."""
import pygame

from .glow import GlowSet

WHITE = (255, 255, 255)


def light_strength(darkness):
    """How bright the lights shine: nothing in daylight, full once it's properly dark."""
    return max(0.0, min(1.0, (darkness - 0.15) / 0.5))


class LightingRenderer:
    """Ground lights go into a light map that multiplies the scene, so they reveal what's under
    them; emissive lights (bulbs, lamps) are added on top afterwards so they keep shining."""

    def __init__(self, size, sources):
        self.sources = sources
        glows = {}
        for src in sources:
            glows.update(src.glows())
        self.glows = GlowSet(glows)
        self.light_map = pygame.Surface(size).convert()

    def draw(self, dst, cam, scene, ambient, darkness, occluded=None):
        """occluded(light, screen_pos) -> True hides an emissive light that's behind something.
        Ground light isn't occluded: it lights whatever was drawn at that spot."""
        if ambient == WHITE:
            return   # multiplying by white changes nothing: daylight costs nothing
        glows = self.glows.at(light_strength(darkness))
        ground, emissive = [], []
        for src in self.sources:
            for light in src.lights(scene, darkness):
                (emissive if light.emissive else ground).append(light)

        lm = self.light_map
        lm.fill(ambient)
        for light in ground:
            self._put(lm, glows[light.glow], cam.to_screen(light.pos, light.z))
        dst.blit(lm, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        for light in emissive:
            s = cam.to_screen(light.pos, light.z)
            if occluded is None or not occluded(light, s):
                self._put(dst, glows[light.glow], s)

    @staticmethod
    def _put(dst, glow, centre):
        dst.blit(glow, glow.get_rect(center=(round(centre.x), round(centre.y))),
                 special_flags=pygame.BLEND_RGB_ADD)
