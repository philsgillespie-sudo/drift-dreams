"""How impacts feel: sounds, camera shake and pad rumble, decided from the drive's events."""
from .events import CarsCollided, Crashed, PropKnocked, WallHit

WALL_FELT, WALL_HEAVY = 60, 170       # a player into a wall: audible, and a crash
CARS_FELT, CARS_HEAVY = 120, 280      # car into car: audible, and (for a player) a crash
PROP_FELT = 30


class Feedback:
    def __init__(self, bus, players, sound, rumble):
        """players: the session's list of Players (it changes as players join and leave);
        rumble(slot, strength, ms) shakes that player's pads."""
        self.bus, self.players, self.sound, self.rumble = bus, players, sound, rumble
        bus.subscribe(WallHit, self._on_wall)
        bus.subscribe(CarsCollided, self._on_cars)
        bus.subscribe(PropKnocked, self._on_prop)
        bus.subscribe(Crashed, self._on_crash)

    def _player_of(self, car):
        return next((p for p in self.players if p.car is car), None)

    def _on_wall(self, e):
        p = self._player_of(e.car)
        if p is None or e.impact <= WALL_FELT:
            return
        heavy = e.impact > WALL_HEAVY
        self.sound.play("crash_heavy" if heavy else "crash_light", min(1.0, e.impact / 300), pos=e.car.pos)
        if heavy:
            self.bus.publish(Crashed(e.car))
        else:
            p.camera.add_shake(3)

    def _on_cars(self, e):
        hit = [p for p in self.players if p.car is e.a or p.car is e.b]
        if hit:
            if e.impact > CARS_FELT:
                self.sound.play("crash_heavy" if e.impact > CARS_HEAVY else "crash_light", pos=e.a.pos)
                for p in hit:
                    p.camera.add_shake(5)
                    self.rumble(p.slot, 0.5, 150)
                    if e.impact > CARS_HEAVY:
                        self.bus.publish(Crashed(p.car))
        elif e.impact > CARS_FELT:
            self.sound.play("crash_light", 0.6, pos=e.a.pos)

    def _on_prop(self, e):
        if e.speed > PROP_FELT:
            self.sound.play("cone_hit", min(1.0, e.speed / 200), pos=e.prop.pos)

    def _on_crash(self, e):
        p = self._player_of(e.car)
        if p is not None:
            p.camera.add_shake(8)
            self.rumble(p.slot, 1.0, 250)
