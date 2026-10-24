"""Arcade drift physics, carried over from the drifting game at half the scale (a car is 30 units long)."""
import math

from pygame.math import Vector2 as V

ENGINE = 380
BRAKE = 700
REVERSE_MAX = 130
DRAG = 0.0015         # quadratic air drag  -> top speed ~400 units/s
ROLL = 0.35           # linear rolling resistance
COAST = 60            # engine braking when no pedal is pressed
TURN_RATE = 3.3       # max yaw rate in grip mode (rad/s)
GRIP = 7.5            # how fast sideways velocity dies when gripping
DRIFT_GRIP = 3.2      # ... while drifting
HANDBRAKE_GRIP = 1.0  # ... with the handbrake on
HANDBRAKE_DECEL = 100
MAX_DRIFT_ANGLE = 1.05   # slip angle the car holds at full steer in a drift
DRIFT_YAW_K = 6.0        # how quickly the body swings to the requested drift angle
DRIFT_SPEED_KEEP = 0.55  # share of lost sideways speed fed back into forward speed
DRIFT_ENTER_SLIP = 0.25  # slip angle that kicks the car into a drift on its own
DRIFT_EXIT_SLIP = 0.06   # drift ends once slip falls below this (handbrake off)
STEER_SPEED = 7.0
CAR_RADIUS = 13

# grip multiplier, extra rolling resistance
SURFACES = {
    "road": (1.0, 0.0),
    "gravel": (0.6, 1.6),
    "grass": (0.5, 1.1),
}


def wrap_angle(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def heading_of(v):
    """Angle measured clockwise from world north (-y), matching the car sprites."""
    return math.atan2(v.x, -v.y)


class Car:
    parked = False      # parked cars sit still until shoved, and don't push street furniture about

    def __init__(self, pos, heading, stack):
        self.stack = stack  # IsoStack in this car's paint
        self.pos = V(pos)
        self.vel = V()
        self.heading = heading
        self.angvel = 0.0
        self.steer = 0.0
        self.drifting = False
        self.slip = 0.0
        self.throttle = 0.0
        self.surface = "road"
        self.on_kerb = False
        self.prev_wheels = None

    def fwd(self):
        return V(math.sin(self.heading), -math.cos(self.heading))

    def rear_wheels(self):
        f = self.fwd()
        r = V(-f.y, f.x)
        back = self.pos - f * 10
        return back - r * 6, back + r * 6

    def update(self, dt, throttle, brake, steer_in, handbrake):
        grip_mul, roll_extra = SURFACES[self.surface]
        self.throttle = throttle
        self.steer += max(-STEER_SPEED * dt, min(STEER_SPEED * dt, steer_in - self.steer))
        f = self.fwd()
        r = V(-f.y, f.x)
        vf, vl = self.vel.dot(f), self.vel.dot(r)

        # engine, brakes, resistance (throttle and brake are 0..1 for analog triggers)
        acc = 0.0
        if throttle:
            acc += ENGINE * throttle
        if brake and vf <= 15 and not throttle and vf > -REVERSE_MAX:
            acc -= ENGINE * 0.6 * brake
        acc -= DRAG * vf * abs(vf) + (ROLL + roll_extra) * vf
        vf += acc * dt
        fric = 0.0
        if brake and vf > 15:
            fric += BRAKE * brake
        if handbrake:
            fric += HANDBRAKE_DECEL
        if not throttle and not brake:
            fric += COAST
        vf = math.copysign(max(0.0, abs(vf) - fric * dt), vf)

        # drift state machine
        speed = math.hypot(vf, vl)
        self.slip = math.atan2(vl, max(abs(vf), 1.0))
        if abs(vf) > 90 and abs(self.steer) > 0.1 and (handbrake or (brake and throttle)):
            self.drifting = True
        if abs(self.slip) > DRIFT_ENTER_SLIP and speed > 100:
            self.drifting = True
        if self.drifting and ((not handbrake and abs(self.slip) < DRIFT_EXIT_SLIP) or speed < 60):
            self.drifting = False

        grip = HANDBRAKE_GRIP if handbrake else DRIFT_GRIP if self.drifting else GRIP
        grip *= grip_mul
        new_vl = vl * math.exp(-grip * dt)
        if self.drifting and throttle and vf > 0:
            vf += abs(vl - new_vl) * DRIFT_SPEED_KEEP
        vl = new_vl

        # yaw
        dirn = 1 if vf >= -3 else -1
        spd = abs(vf)
        if self.drifting or handbrake:
            # steering picks the slip angle; the body swings toward it while the
            # velocity is dragged round by the remaining grip
            vel_turn = -grip * vl * vf / max(speed * speed, 1.0)
            want = -self.steer * MAX_DRIFT_ANGLE * (0.75 + 0.25 * throttle)
            target = vel_turn + (self.slip - want) * DRIFT_YAW_K
            resp = 7.0
        else:
            turn = TURN_RATE * min(1.0, spd / 80) / (1 + spd / 550)
            target = self.steer * turn * dirn
            resp = 10.0
        self.angvel += (target - self.angvel) * min(1.0, resp * dt)
        self.heading = wrap_angle(self.heading + self.angvel * dt)

        self.vel = f * vf + r * vl
        self.pos += self.vel * dt

    def image(self):
        return self.stack.image(math.degrees(self.heading))
