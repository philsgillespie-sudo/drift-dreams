import pygame

from . import state
from .state import DriveControls

ACTION_KEYS = {
    pygame.K_LEFT: state.LEFT,
    pygame.K_a: state.LEFT,
    pygame.K_RIGHT: state.RIGHT,
    pygame.K_d: state.RIGHT,
    pygame.K_RETURN: state.CONFIRM,
    pygame.K_KP_ENTER: state.CONFIRM,
    pygame.K_SPACE: state.SELECT,
    pygame.K_ESCAPE: state.BACK,
    pygame.K_r: state.RESTART,
    pygame.K_t: state.RESET,
    pygame.K_LEFTBRACKET: state.TIME_BACK,
    pygame.K_RIGHTBRACKET: state.TIME_FWD,
    pygame.K_2: state.JOIN,
    pygame.K_F2: state.JOIN,
}

# Two players on one keyboard: the left half is player 1's, the right half player 2's.
LEFT_ACTION_KEYS = {
    pygame.K_a: state.LEFT,
    pygame.K_d: state.RIGHT,
    pygame.K_SPACE: state.SELECT,
    pygame.K_ESCAPE: state.BACK,
    pygame.K_r: state.RESTART,
    pygame.K_t: state.RESET,
    pygame.K_LEFTBRACKET: state.TIME_BACK,
    pygame.K_RIGHTBRACKET: state.TIME_FWD,
    pygame.K_2: state.JOIN,
    pygame.K_F2: state.JOIN,
}
RIGHT_ACTION_KEYS = {
    pygame.K_LEFT: state.LEFT,
    pygame.K_RIGHT: state.RIGHT,
    pygame.K_RETURN: state.CONFIRM,
    pygame.K_KP_ENTER: state.CONFIRM,
    pygame.K_BACKSPACE: state.BACK,
    pygame.K_SLASH: state.RESET,
}

# (throttle, brake, left, right, handbrake keys)
WHOLE = ((pygame.K_UP, pygame.K_w), (pygame.K_DOWN, pygame.K_s), (pygame.K_LEFT, pygame.K_a),
         (pygame.K_RIGHT, pygame.K_d), (pygame.K_SPACE,))
LEFT_HALF = ((pygame.K_w,), (pygame.K_s,), (pygame.K_a,), (pygame.K_d,), (pygame.K_SPACE, pygame.K_LSHIFT))
RIGHT_HALF = ((pygame.K_UP,), (pygame.K_DOWN,), (pygame.K_LEFT,), (pygame.K_RIGHT,), (pygame.K_RCTRL, pygame.K_RSHIFT))

HINTS = {
    "whole": "ARROWS/WASD drive  SPACE drift  T to road  R start",
    "left": "WASD drive  SPACE/L-SHIFT drift  T to road  R start",
    "right": "ARROWS drive  R-CTRL/R-SHIFT drift  / to road",
}


class Keyboard:
    """The whole keyboard, or (split) its left half and its right half as two devices."""
    name = "Keyboard"

    def actions(self, event, half="whole"):
        """half: "whole", "left" or "right"."""
        if event.type != pygame.KEYDOWN:
            return []
        keys = {"whole": ACTION_KEYS, "left": LEFT_ACTION_KEYS, "right": RIGHT_ACTION_KEYS}[half]
        return [keys[event.key]] if event.key in keys else []

    def drive(self, half="whole"):
        keys = pygame.key.get_pressed()
        gas, brake, left, right, hand = {"whole": WHOLE, "left": LEFT_HALF, "right": RIGHT_HALF}[half]
        held = lambda ks: any(keys[k] for k in ks)  # noqa: E731
        return DriveControls(
            throttle=1.0 if held(gas) else 0.0,
            brake=1.0 if held(brake) else 0.0,
            steer=float(held(right) - held(left)),
            handbrake=held(hand),
        )
