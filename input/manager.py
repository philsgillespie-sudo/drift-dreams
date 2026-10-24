import pygame

from .gamepad import Gamepad, sdl_controller
from .keyboard import HINTS, Keyboard
from .state import DriveControls

HOTPLUG_EVENTS = {
    pygame.JOYDEVICEADDED,
    pygame.JOYDEVICEREMOVED,
    getattr(pygame, "CONTROLLERDEVICEADDED", -1),
    getattr(pygame, "CONTROLLERDEVICEREMOVED", -1),
}
PAD_HINT = "RT gas  LT brake  A/RB drift  Y to road"


class InputManager:
    """Keyboard plus any number of gamepads, usable at the same time, split between one or two
    players ("slots" 0 and 1).

    One player: every device steers slot 0. Two players: with two or more pads, pad 1 is player 2's
    and pad 0 and the keyboard are player 1's; with one pad, the pad is player 1's and the keyboard
    player 2's; with none, the keyboard splits in half. Pads are numbered in the order they
    connected. In one-player mode a second pad still reports its actions as slot 1, so it can join.

    Each frame: feed every pygame event to handle_event(), then call poll_actions() and drive(slot).
    Actions come as (slot, action) pairs.
    """

    def __init__(self):
        pygame.joystick.init()
        if sdl_controller:
            sdl_controller.init()
        self.keyboard = Keyboard()
        self.pads = []
        self.players = 1
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
        self.pads.sort(key=lambda p: p.id)   # first connected first, whatever SDL's index order
        after = [p.name for p in self.pads]
        for name in after:
            if name not in before:
                self.notices.append(f"{name} connected")
        for name in before:
            if name not in after:
                self.notices.append(f"{name} disconnected")

    # -- who steers which slot ---------------------------------------------------
    def _keyboard(self):
        """[(half, slot)] for the keyboard."""
        if len(self.pads) >= 2 or self.players == 1:
            return [("whole", 0)]
        if len(self.pads) == 1:
            return [("whole", 1)]
        return [("left", 0), ("right", 1)]

    def _pad_slot(self, k):
        """Slot of the k-th pad, or None if it steers nobody."""
        if len(self.pads) == 1:
            return 0
        return k if k < 2 else None

    def _pads(self, slot):
        return [pad for k, pad in enumerate(self.pads) if self._pad_slot(k) == slot]

    @property
    def has_gamepad(self):
        return bool(self.pads)

    @property
    def gamepad_name(self):
        return self.pads[0].name if self.pads else None

    def device_name(self, slot):
        """What steers this slot, for the menu."""
        pads = self._pads(slot)
        if pads:
            return f"Controller: {pads[0].name}"
        halves = [h for h, s in self._keyboard() if s == slot]
        if not halves:
            return None
        return {"whole": "Keyboard", "left": "Keyboard: left half (WASD)",
                "right": "Keyboard: right half (arrows)"}[halves[0]]

    def hint(self, slot):
        """The controls in one line, for the HUD."""
        if self._pads(slot):
            return PAD_HINT
        halves = [h for h, s in self._keyboard() if s == slot]
        return HINTS[halves[0]] if halves else ""

    # -- reading -----------------------------------------------------------------
    def handle_event(self, event):
        """Returns the (slot, action) pairs this event triggered."""
        if event.type in HOTPLUG_EVENTS:
            self._rescan()
            return []
        return [(slot, a) for half, slot in self._keyboard() for a in self.keyboard.actions(event, half)]

    def poll_actions(self):
        out = []
        for k, pad in enumerate(self.pads):
            slot = self._pad_slot(k)
            for a in pad.actions():
                if slot is not None:
                    out.append((slot, a))
        return out

    def take_notices(self):
        out, self.notices = self.notices, []
        return out

    def drive(self, slot=0):
        controls = DriveControls()
        for half, s in self._keyboard():
            if s == slot:
                controls = controls.merge(self.keyboard.drive(half))
        for pad in self._pads(slot):
            controls = controls.merge(pad.drive())
        return controls

    def rumble(self, slot=0, strength=1.0, ms=200):
        for pad in self._pads(slot):
            pad.rumble(strength, ms)
