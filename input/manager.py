import pygame

from .gamepad import Gamepad, sdl_controller
from .keyboard import Keyboard
from .state import DriveControls

HOTPLUG_EVENTS = {
    pygame.JOYDEVICEADDED,
    pygame.JOYDEVICEREMOVED,
    getattr(pygame, "CONTROLLERDEVICEADDED", -1),
    getattr(pygame, "CONTROLLERDEVICEREMOVED", -1),
}


class InputManager:
    """Keyboard plus any number of gamepads, usable at the same time.

    Each frame: feed every pygame event to handle_event(), then call
    poll_actions() and drive().
    """

    def __init__(self):
        pygame.joystick.init()
        if sdl_controller:
            sdl_controller.init()
        self.keyboard = Keyboard()
        self.pads = []
        self.notices = []  # human-readable connect/disconnect messages
        self._rescan()
        self.notices.clear()  # pads present at launch aren't news

    def _rescan(self):
        before = [p.name for p in self.pads]
        for p in self.pads:
            p.close()
        self.pads = []
        for i in range(pygame.joystick.get_count()):
            try:
                self.pads.append(Gamepad(i))
            except pygame.error:
                pass
        after = [p.name for p in self.pads]
        for name in after:
            if name not in before:
                self.notices.append(f"{name} connected")
        for name in before:
            if name not in after:
                self.notices.append(f"{name} disconnected")

    @property
    def has_gamepad(self):
        return bool(self.pads)

    @property
    def gamepad_name(self):
        return self.pads[0].name if self.pads else None

    def handle_event(self, event):
        """Returns the actions this event triggered."""
        if event.type in HOTPLUG_EVENTS:
            self._rescan()
            return []
        return self.keyboard.actions(event)

    def poll_actions(self):
        return [a for pad in self.pads for a in pad.actions()]

    def take_notices(self):
        out, self.notices = self.notices, []
        return out

    def drive(self):
        controls = self.keyboard.drive()
        for pad in self.pads:
            controls = controls.merge(pad.drive())
        return controls

    def rumble(self, strength=1.0, ms=200):
        for pad in self.pads:
            pad.rumble(strength, ms)
