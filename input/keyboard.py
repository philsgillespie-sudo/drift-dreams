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
}


class Keyboard:
    name = "Keyboard"

    def actions(self, event):
        if event.type == pygame.KEYDOWN and event.key in ACTION_KEYS:
            return [ACTION_KEYS[event.key]]
        return []

    def drive(self):
        keys = pygame.key.get_pressed()
        return DriveControls(
            throttle=1.0 if keys[pygame.K_UP] or keys[pygame.K_w] else 0.0,
            brake=1.0 if keys[pygame.K_DOWN] or keys[pygame.K_s] else 0.0,
            steer=float((keys[pygame.K_RIGHT] or keys[pygame.K_d])
                        - (keys[pygame.K_LEFT] or keys[pygame.K_a])),
            handbrake=bool(keys[pygame.K_SPACE]),
        )
