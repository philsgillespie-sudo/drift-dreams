"""Cops and robbers: the match, its rounds and who plays which part.

A round runs through phases (HeadStart -> Pursuit -> RoundResult) and the match ends on MatchResult.
The rules only decide: they publish what happened (game.events) and the announcer, the livery and
the HUD show it.
"""
import math
import random

from .. import config
from ..events import BUSTED, LOST, TIME_UP, CarsCollided, Countdown, MatchOver, RoundOver, RoundStarted
from .meters import BustMeter, GetawayMeter


class Phase:
    """One stretch of a match. update() returns the phase that follows, or None to carry on."""
    cop_held = False      # the cop sits still at the start line
    final = False         # the match is over
    can_restart = False   # a rematch can start now

    def enter(self, chase):
        pass

    def update(self, chase, dt):
        return None

    def on_cars(self, chase, e):
        """A CarsCollided event."""
        pass


class HeadStart(Phase):
    """The robber is off; the cop waits out the countdown."""
    cop_held = True

    def __init__(self):
        self.left = float(config.HEAD_START)

    def enter(self, chase):
        chase.bus.publish(Countdown(config.HEAD_START))

    def update(self, chase, dt):
        before = math.ceil(self.left)
        self.left -= dt
        if self.left <= 0:
            chase.bus.publish(Countdown(0))
            return Pursuit()
        if math.ceil(self.left) < before:
            chase.bus.publish(Countdown(math.ceil(self.left)))
        return None


class Pursuit(Phase):
    """The chase proper: a bust, a getaway or the clock running out ends it."""

    def __init__(self):
        self.left = config.ROUND_TIME
        self.bust, self.getaway = BustMeter(), GetawayMeter()

    def update(self, chase, dt):
        cop, robber = chase.cop.car, chase.robber.car
        self.left = max(0.0, self.left - dt)
        self.bust.update(dt, cop, robber)
        self.getaway.update(dt, cop, robber)
        if self.bust.full:
            return chase.end_round(chase.cop, BUSTED)
        if self.getaway.full:
            return chase.end_round(chase.robber, LOST)
        if self.left <= 0:
            return chase.end_round(chase.robber, TIME_UP)
        return None

    def on_cars(self, chase, e):
        cop, robber = chase.cop.car, chase.robber.car
        if (e.a is cop and e.b is robber) or (e.a is robber and e.b is cop):
            self.bust.ram(e.impact)


class RoundResult(Phase):
    """The round's outcome on screen for a moment, then the next round (or the match result)."""

    def __init__(self, winner, how):
        self.winner, self.how = winner, how
        self.left = config.RESULT_TIME

    def update(self, chase, dt):
        self.left -= dt
        return chase.next_round() if self.left <= 0 else None


class MatchResult(Phase):
    """Someone has won; waits for a rematch (not straight away, so a button still held can't skip it)."""
    final = True

    def __init__(self, winner):
        self.winner = winner
        self.shown = 0.0

    @property
    def can_restart(self):
        return self.shown > config.REMATCH_DELAY

    def update(self, chase, dt):
        self.shown += dt
        return None


class Chase:
    """A match between the session's two players. Roles swap every round; the first cop is picked at random."""

    def __init__(self, bus, session, rng=random):
        self.bus, self.session, self.rng = bus, session, rng
        self.players = session.players[:2]
        self.phase = Phase()
        bus.subscribe(CarsCollided, self._on_cars)
        self.start()

    def detach(self):
        self.bus.unsubscribe(CarsCollided, self._on_cars)

    # -- asking ----------------------------------------------------------------
    @property
    def over(self):
        return self.phase.final

    def role_of(self, player):
        return config.COP if player is self.cop else config.ROBBER

    def other(self, player):
        return self.players[1] if player is self.players[0] else self.players[0]

    def held(self, player):
        """Whether this player's car is kept still."""
        return player is self.cop and self.phase.cop_held

    # -- running -----------------------------------------------------------------
    def start(self):
        """A new match."""
        self.wins = [0] * len(self.players)
        self.round = 0
        self._switch(self._start_round(self.rng.choice(self.players)))

    def rematch(self):
        """A new match if this one is over (and its result has been seen); whether it started."""
        if not self.phase.can_restart:
            return False
        self.start()
        return True

    def update(self, dt):
        nxt = self.phase.update(self, dt)
        if nxt is not None:
            self._switch(nxt)

    def end_round(self, winner, how):
        self.wins[winner.index] += 1
        self.bus.publish(RoundOver(winner, self.other(winner), how))
        return RoundResult(winner, how)

    def next_round(self):
        leader = max(self.players, key=lambda p: self.wins[p.index])
        if self.wins[leader.index] >= config.MATCH_WINS:
            self.bus.publish(MatchOver(leader, self.other(leader)))
            return MatchResult(leader)
        return self._start_round(self.robber)     # swap: last round's robber chases

    def _start_round(self, cop):
        self.cop, self.robber = cop, self.other(cop)
        self.round += 1
        self.session.line_up(self.robber, self.cop, config.START_GAP)
        self.bus.publish(RoundStarted(self.round, self.cop, self.robber))
        return HeadStart()

    def _switch(self, phase):
        self.phase = phase
        phase.enter(self)

    def _on_cars(self, e):
        self.phase.on_cars(self, e)
