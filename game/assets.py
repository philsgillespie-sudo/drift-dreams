"""Everything loaded from disk and pre-rendered before play starts."""
import pygame

from districts import DistrictArt
from iso import IsoStack, load_atlas, load_pivots, ramp, stack_slices, stripe_ramp

from . import config
from .props import PROP_TYPES


def paint_map(body, stripe=None):
    """Colour swaps from the sheet's red paint to `body`; no stripe paints the stripes over."""
    base = config.BASE_PAINT
    new = ramp(body)
    pairs = list(zip(ramp(base[0]), new))
    pairs += zip(stripe_ramp(base[1]), stripe_ramp(stripe) if stripe else new[1:4])
    return [(pygame.Color(a), pygame.Color(b)) for a, b in pairs]


class Assets:
    """Sprites and sprite stacks. progress(message) is called before each slow step."""

    def __init__(self, progress=lambda msg: None):
        folder = config.SPRITES
        progress("Loading sprites...")
        tiles, _ = load_atlas(folder, "tiles")
        tiles.update(load_atlas(folder, "bridge_tiles")[0])
        self.decos = {}      # name -> (surface, pivot)
        for sheet in ("bridge_rails", "bridge_towers"):
            frames, pivots = load_atlas(folder, sheet)[0], load_pivots(folder, sheet)
            self.decos.update({k: (f, pivots[k]) for k, f in frames.items()})
        buildings, _ = load_atlas(folder, "buildings")
        self.district_art = DistrictArt(tiles, buildings)
        car_f, _ = load_atlas(folder, "car_stack")
        prop_f, _ = load_atlas(folder, "props_stack")
        scen_f, _ = load_atlas(folder, "scenery_stack")
        fx_f, fx_anims = load_atlas(folder, "fx")
        self.smoke_frames = [fx_f[k] for k in fx_anims["smoke"]]

        progress("Painting cars...")
        coupe = IsoStack(stack_slices(car_f, "coupe"), steps=72)
        self.player_stacks = {name: coupe.recolored(paint_map(*p)) for name, p in config.PLAYER_PAINTS.items()}
        self.police_stack = coupe.recolored(paint_map(*config.POLICE_PAINT))
        models = [IsoStack(stack_slices(car_f, m), steps=72) for m in config.TRAFFIC_MODELS]
        self.traffic_stacks = [s.recolored(paint_map(p)) for s in models for p in config.TRAFFIC_PAINTS]
        self.prop_stacks = {k: IsoStack(stack_slices(prop_f, k), steps=24) for k in PROP_TYPES}
        self.scenery = {k: IsoStack(stack_slices(scen_f, k), steps=4, shadow=k != "lamp") for k in config.SCENERY}
