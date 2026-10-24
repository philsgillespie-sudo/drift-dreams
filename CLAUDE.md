# Drift Dreams

Open-world isometric drifting game in Python + pygame 2.6 (Python 3.13, Windows). Entry point `drift_dreams.py`.

## Run / check
- Play: `run.bat` or `py drift_dreams.py [--time HOUR] [--no-vsync]`
- Frame-time profile (headless, no window): `py tools/frame_profile.py [--frames N] [--hour H] [--cprofile]`.
  Baseline after the 2026-10 refactor: mean ~6-8 ms, p99 ~10-12 ms at night. Budget is 16.7 ms (60 fps).
- Headless anything: set `SDL_VIDEO_DRIVER=dummy` and `SDL_AUDIODRIVER=dummy` before importing pygame.
  `Game.update(dt)` / `Game.draw()` can be stepped by hand; `game.autopilot = fn(game) -> DriveControls` drives the player.
- No tests. Lint with `py -m pyflakes <paths>`.
- Git is not on PATH: `C:\Program Files\Git\cmd\git.exe`. Pushing needs GitHub sign-in, which only works in an
  interactive terminal (run it in the user's Terminal panel, not the non-interactive shell). Remote: github.com/philsgillespie-sudo/drift-dreams

## Map
- `game/` the game. `app.py` Game: window, loop, wiring. `session.py` Session: the simulation, stepped per frame
  (same object behind menu and drive). Systems: `collisions.py`, `props.py`, `combo.py` (scoring), `effects.py`
  (particles, skids), `feedback.py` (sound/shake/rumble). `scenes.py` MenuScene/DriveScene (state pattern).
  `render/` WorldRenderer (depth-sorted world), Hud, MenuView, Text (cached). `config.py` tunables, `events.py` events.
- `districts/` map pieces: `base.py` District (ground chunks, building blocks, skid marks), `city.py`, `bridge.py`;
  `LAYOUT` in `__init__.py` builds them in order.
- `world.py` joins districts: flat tile lookup, collision, road graph, minimap. `roads.py` RoadGraph.
- `traffic.py` AI cars on the RoadGraph. `car.py` drift physics. `core/` EventBus, SpatialHash.
- Untouched by the refactor: `iso/` camera + sprite stacks, `lighting/`, `sound/`, `input/`.
- Assets are generated: sprites from `sprites_src/` by `tools/gen_sprites.py`, sfx by `sound/gen_sfx.py`.

Frame order (`Game.update`): sound -> scene -> Session.update (clock, player, traffic, collisions, surfaces,
tyres, props, combo if scoring, particles) -> popups -> camera. Draw: ground -> fresh skid marks -> things sorted
by (depth = x + y, tiebreak) -> lighting -> scene overlay.

## Extending
- District: subclass `District`, fill ground/solid/buildings/statics, implement `add_roads(graph)` (and
  `building_image` if it has buildings), add a builder to `districts.LAYOUT`. Traffic and "back to road" follow.
- Prop kind: entry in `game/props.py PROP_TYPES` (+ stack in props_stack sheet).
- Game mode: a `Scene` subclass registered in `Game.scenes`.
- Thing on the map: a source + a drawer in `WorldRenderer` (`sources`, `drawers`).
- Reacting to gameplay: `bus.subscribe(EventType, handler)`; publish new event dataclasses from `game/events.py`.

## Rules that aren't obvious (performance and correctness)
- Buildings draw as **square** `BuildingBlock`s: a square footprint sorts by one depth (x0+y1 == x1+y0) like a tile.
  Non-square blocks break depth sorting against cars/props.
- Ground chunks are RLE colorkey surfaces: ~7x faster to blit but ~1.7 ms to modify. Skid marks are drawn on screen
  first and painted into chunks in batches (`MARK_BATCH`/`MARK_WAIT`).
- At most one slow job per frame per district (chunk bake, mark batch, block image); see `District.draw_ground`.
- Surfaces blitted every frame must be display format (`convert`/`convert_alpha`); `IsoStack` does this itself.
- Don't allocate surfaces or render text per frame: cache them (`Text`, `MenuView`, `Hud.panel`).
- Faded (x-ray) buildings use `set_alpha` on the shared image and reset it straight after; they don't occlude lights.
- Startup (~4.5 s) is mostly `IsoStack` pre-rendering car/prop headings in pure Python.
