from dataclasses import dataclass


@dataclass
class DriveControls:
    """What the player is asking the car to do this frame.

    throttle/brake are 0..1 (analog on triggers), steer is -1 (left) .. 1 (right).
    """
    throttle: float = 0.0
    brake: float = 0.0
    steer: float = 0.0
    handbrake: bool = False

    def merge(self, other):
        """Combine two devices: strongest pedal wins, first non-zero steer wins."""
        return DriveControls(
            throttle=max(self.throttle, other.throttle),
            brake=max(self.brake, other.brake),
            steer=self.steer if self.steer else other.steer,
            handbrake=self.handbrake or other.handbrake,
        )


# One-shot actions the game reacts to (menus, restart, ...).
LEFT = "left"
RIGHT = "right"
CONFIRM = "confirm"   # Enter / Start: start or restart a race
SELECT = "select"     # Space / A: pick in the menu
BACK = "back"         # Esc / Back: leave the race, quit from the menu
RESTART = "restart"
RESET = "reset"       # put the car back on the track
TIME_BACK = "time_back"   # debug: clock back an hour
TIME_FWD = "time_fwd"     # debug: clock on an hour
