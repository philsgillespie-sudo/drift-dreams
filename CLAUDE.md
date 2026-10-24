# Drift Dreams

Open-world isometric drifting game in Python + pygame 2.6 (Python 3.13, Windows). Entry point `drift_dreams.py`.

## Run / check
- Play: `run.bat` or `py drift_dreams.py [--time HOUR] [--no-vsync] [--players 2]` (or press 2 in the menu)
- Frame-time profile (headless, no window): `py tools/frame_profile.py [--frames N] [--hour H] [--players 2] [--cprofile]`.
  Baseline at night: one player mean ~5 ms, p99 ~8.5 ms; two players mean ~12 ms, p99 ~18 ms (2.4 ms of
  it is the headless software upload of player 2's window). Budget is 16.7 ms (60 fps).
- Headless anything: set `SDL_VIDEO_DRIVER=dummy` and `SDL_AUDIODRIVER=dummy` before importing pygame.
  `Game.update(dt)` / `Game.draw()` can be stepped by hand; `game.autopilot = fn(game) -> DriveControls` drives
  player 1, `game.autopilot2` player 2. `Game(players=2)` / `game.add_player()` adds player 2 (works headless too).
- No tests. Lint with `py -m pyflakes <paths>`.
- Git is not on PATH: `C:\Program Files\Git\cmd\git.exe`. Pushing needs GitHub sign-in, which only works in an
  interactive terminal (run it in the user's Terminal panel, not the non-interactive shell). Remote: github.com/philsgillespie-sudo/drift-dreams

## Map
- `game/` the game. `app.py` Game: windows, loop, wiring. `session.py` Session: the simulation, stepped per frame
  (same object behind menu and drive). `players.py` Player: car + combo + camera; `Session.players` holds one or two
  (`session.player` is player 1's car). Systems: `collisions.py`, `props.py`, `combo.py` (scoring), `effects.py`
  (particles, skids), `feedback.py` (sound/shake/rumble). `scenes.py` MenuScene/DriveScene (state pattern).
  `render/` WorldRenderer (depth-sorted world), Hud, MenuView, Text (cached), SecondWindow (player 2's SDL window). `config.py` tunables, `events.py` events.
- `districts/` map pieces: `base.py` District (ground chunks, building blocks, skid marks), `city.py`, `bridge.py`;
  `LAYOUT` in `__init__.py` builds them in order.
- `world.py` joins districts: flat tile lookup, collision, road graph, minimap. `roads.py` RoadGraph.
- `traffic.py` AI cars on the RoadGraph. `car.py` drift physics. `core/` EventBus, SpatialHash.
- Untouched by the refactor: `iso/` camera + sprite stacks, `lighting/`, `sound/`, `input/`.
- Assets are generated: sprites from `sprites_src/` by `tools/gen_sprites.py`, sfx by `sound/gen_sfx.py`.

Frame order (`Game.update`): sound -> scene -> Session.update (clock, players, traffic, collisions, surfaces,
tyres, props, combos if scoring, particles) -> popups -> cameras. Draw, per player (player 2 first): ground ->
fresh skid marks -> things sorted by (depth = x + y, tiebreak) -> lighting -> scene overlay; then
`World.end_frame` (background baking, once a frame).

## Two players
- Input slots 0/1 (`InputManager`): with 2+ pads pad 1 is P2; with 1 pad the pad is P1 and the keyboard P2;
  with none the keyboard splits (WASD+Space/LShift vs arrows+RCtrl, Enter, Backspace, `/`). Actions arrive as
  (slot, action); a slot with no player yet joins on CONFIRM/SELECT.
- Events about a player carry its car (`Crashed`, `PropSmashed`, `PlayerPlaced`; `Message.car`, None = everyone);
  per-player systems (Combo, Popups, Feedback) filter on it. Traffic spawns out of sight of every camera.
- One sound card: sounds are heard from the nearest player.

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
- At most one slow job per frame per district (chunk bake, mark batch, block image); see `District.end_frame`.
- Every view draws on the main window's surface (P2's is uploaded to its window before P1 draws). SDL re-encodes
  an RLE surface whenever it's blitted to a different surface than last time: a second target surface made the
  ground cost 2-3x.
- Surfaces blitted every frame must be display format (`convert`/`convert_alpha`); `IsoStack` does this itself.
- Don't allocate surfaces or render text per frame: cache them (`Text`, `MenuView`, `Hud.panel`).
- Faded (x-ray) buildings use `set_alpha` on the shared image and reset it straight after; they don't occlude lights.
- Startup (~4.5 s) is mostly `IsoStack` pre-rendering car/prop headings in pure Python.
