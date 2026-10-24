"""How impacts feel: sounds, camera shake and pad rumble, decided from the drive's events."""
from .events import CarsCollided, Crashed, PropKnocked, WallHit

WALL_FELT, WALL_HEAVY = 60, 170       # player into a wall: audible, and a crash
CARS_FELT, CARS_HEAVY = 120, 280      # car into car: audible, and (for the player) a crash
PROP_FELT = 30


class Feedback:
    def __init__(self, bus, player, sound, camera, rumble):
        """player: the player's car; rumble(strength, ms) shakes the pads."""
        self.bus, self.player, self.sound, self.camera, self.rumble = bus, player, sound, camera, rumble
        bus.subscribe(WallHit, self._on_wall)
        bus.subscribe(CarsCollided, self._on_cars)
        bus.subscribe(PropKnocked, self._on_prop)
        bus.subscribe(Crashed, self._on_crash)

    def _on_wall(self, e):
        if e.car is not self.player or e.impact <= WALL_FELT:
            return
        heavy = e.impact > WALL_HEAVY
        self.sound.play("crash_heavy" if heavy else "crash_light", min(1.0, e.impact / 300))
        if heavy:
            self.bus.publish(Crashed())
        else:
            self.camera.add_shake(3)

    def _on_cars(self, e):
        if self.player in (e.a, e.b):
            other = e.b if e.a is self.player else e.a
            if e.impact > CARS_FELT:
                self.sound.play("crash_heavy" if e.impact > CARS_HEAVY else "crash_light", pos=other.pos)
                self.camera.add_shake(5)
                self.rumble(0.5, 150)
                if e.impact > CARS_HEAVY:
                    self.bus.publish(Crashed())
        elif e.impact > CARS_FELT:
            self.sound.play("crash_light", 0.6, pos=e.a.pos)

    def _on_prop(self, e):
        if e.speed > PROP_FELT:
            self.sound.play("cone_hit", min(1.0, e.speed / 200), pos=e.prop.pos)

    def _on_crash(self, e):
        self.camera.add_shake(8)
        self.rumble(1.0, 250)
