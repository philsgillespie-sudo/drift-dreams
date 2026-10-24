import math

import pygame

from . import state
from .state import DriveControls

try:
    from pygame._sdl2 import controller as sdl_controller
except ImportError:  # older pygame builds
    sdl_controller = None

STICK_DEADZONE = 0.15
TRIGGER_DEADZONE = 0.05
MENU_THRESHOLD = 0.6

# SDL GameController names (Xbox naming; PlayStation/Switch pads are remapped by SDL)
MAPPED_AXES = {
    "lx": pygame.CONTROLLER_AXIS_LEFTX,
    "lt": pygame.CONTROLLER_AXIS_TRIGGERLEFT,
    "rt": pygame.CONTROLLER_AXIS_TRIGGERRIGHT,
}
MAPPED_BUTTONS = {
    "a": pygame.CONTROLLER_BUTTON_A,
    "b": pygame.CONTROLLER_BUTTON_B,
    "x": pygame.CONTROLLER_BUTTON_X,
    "y": pygame.CONTROLLER_BUTTON_Y,
    "lb": pygame.CONTROLLER_BUTTON_LEFTSHOULDER,
    "rb": pygame.CONTROLLER_BUTTON_RIGHTSHOULDER,
    "back": pygame.CONTROLLER_BUTTON_BACK,
    "start": pygame.CONTROLLER_BUTTON_START,
    "dleft": pygame.CONTROLLER_BUTTON_DPAD_LEFT,
    "dright": pygame.CONTROLLER_BUTTON_DPAD_RIGHT,
}
# Fallback for devices SDL has no mapping for: assume an XInput-style layout.
RAW_AXES = {"lx": 0, "lt": 4, "rt": 5}
RAW_BUTTONS = {"a": 0, "b": 1, "x": 2, "y": 3, "lb": 4, "rb": 5, "back": 6, "start": 7}

PAD_ACTIONS = {
    "start": state.CONFIRM,
    "a": state.SELECT,
    "back": state.BACK,
    "y": state.RESET,
    "left": state.LEFT,
    "right": state.RIGHT,
}


def deadzone(v, dz):
    if abs(v) < dz:
        return 0.0
    return math.copysign(min(1.0, (abs(v) - dz) / (1 - dz)), v)


class Gamepad:
    """One connected pad.

    Layout: left stick / d-pad steer, RT throttle, LT brake & reverse,
    A or RB handbrake, Y reset to track, Start confirm, Back menu.
    """

    def __init__(self, index):
        self.mapped = bool(sdl_controller and sdl_controller.is_controller(index))
        if self.mapped:
            self.dev = sdl_controller.Controller(index)
            self.name = self.dev.name
        else:
            self.dev = pygame.joystick.Joystick(index)
            self.name = self.dev.get_name()
        self.id = pygame.joystick.Joystick(index).get_instance_id()   # rises with each connection
        # buttons already held when the pad connects shouldn't count as presses
        self._held = self._pressed_now()

    def close(self):
        try:
            self.dev.quit()
        except pygame.error:
            pass

    # -- raw reads ---------------------------------------------------------
    def axis(self, name):
        if self.mapped:
            v = self.dev.get_axis(MAPPED_AXES[name]) / 32767
        else:
            i = RAW_AXES[name]
            if i >= self.dev.get_numaxes():
                return 0.0
            v = self.dev.get_axis(i)
            if name in ("lt", "rt"):
                v = (v + 1) / 2  # raw triggers rest at -1
        return max(-1.0, min(1.0, v))

    def button(self, name):
        if self.mapped:
            return bool(self.dev.get_button(MAPPED_BUTTONS[name]))
        if name in ("dleft", "dright"):
            if self.dev.get_numhats() == 0:
                return False
            hx = self.dev.get_hat(0)[0]
            return hx == (-1 if name == "dleft" else 1)
        i = RAW_BUTTONS[name]
        return i < self.dev.get_numbuttons() and bool(self.dev.get_button(i))

    # -- game-facing -------------------------------------------------------
    def drive(self):
        steer = deadzone(self.axis("lx"), STICK_DEADZONE)
        if self.button("dleft"):
            steer = -1.0
        elif self.button("dright"):
            steer = 1.0
        return DriveControls(
            throttle=deadzone(self.axis("rt"), TRIGGER_DEADZONE),
            brake=deadzone(self.axis("lt"), TRIGGER_DEADZONE),
            steer=steer,
            handbrake=self.button("a") or self.button("rb"),
        )

    def _pressed_now(self):
        now = {b for b in ("start", "a", "back", "y") if self.button(b)}
        x = self.axis("lx")
        if self.button("dleft") or x < -MENU_THRESHOLD:
            now.add("left")
        if self.button("dright") or x > MENU_THRESHOLD:
            now.add("right")
        return now

    def actions(self):
        """Actions for buttons that went down since the last call."""
        now = self._pressed_now()
        pressed = now - self._held
        self._held = now
        return [PAD_ACTIONS[b] for b in pressed]

    def rumble(self, strength, ms):
        try:
            self.dev.rumble(strength * 0.6, strength, ms)
        except (pygame.error, AttributeError):
            pass
