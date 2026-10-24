"""Tells the players how the chase is going: pop-up lines, stings and rumble, from the chase's events."""
from ..events import BUSTED, LOST, Countdown, MatchOver, Message, RoundOver, RoundStarted

GOOD, BAD, NEWS = (120, 255, 140), (255, 90, 90), (255, 214, 60)
# how -> (the winner's line, the loser's line)
OUTCOMES = {
    BUSTED: ("BUSTED THEM!", "BUSTED!"),
    LOST: ("LOST THE COPS!", "THEY SHOOK YOU OFF"),
}
OUT_OF_TIME = ("GOT AWAY!", "OUT OF TIME")


class Announcer:
    def __init__(self, bus, sound, rumble):
        """rumble(slot, strength, ms) shakes that player's pads."""
        self.bus, self.sound, self.rumble = bus, sound, rumble
        bus.subscribe(RoundStarted, self._on_round)
        bus.subscribe(Countdown, self._on_countdown)
        bus.subscribe(RoundOver, self._on_round_over)
        bus.subscribe(MatchOver, self._on_match_over)

    def _say(self, text, color, player=None):
        self.bus.publish(Message(text, color, player.car if player else None))

    def _on_round(self, e):
        self._say(f"ROUND {e.number}: YOU'RE THE COP", NEWS, e.cop)
        self._say(f"ROUND {e.number}: YOU'RE THE ROBBER - DRIVE!", NEWS, e.robber)

    def _on_countdown(self, e):
        self.sound.play("countdown_go" if e.seconds == 0 else "countdown_beep")

    def _on_round_over(self, e):
        won, lost = OUTCOMES.get(e.how, OUT_OF_TIME)
        self._say(won, GOOD, e.winner)
        self._say(lost, BAD, e.loser)
        self.sound.play("lap_complete")
        self.rumble(e.loser.slot, 0.8, 400)

    def _on_match_over(self, e):
        self._say(f"PLAYER {e.winner.index + 1} WINS THE MATCH", NEWS)
        self.sound.play("finish_line")
