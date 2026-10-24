"""How the parts look: the cop drives a police car with its lightbar on, the robber their own paint."""
from ..events import RoundStarted


class Livery:
    def __init__(self, bus, police_stack, paint_stack):
        """paint_stack(player) -> the IsoStack in the paint that player picked."""
        self.police_stack, self.paint_stack = police_stack, paint_stack
        bus.subscribe(RoundStarted, self._on_round)

    def _on_round(self, e):
        e.cop.car.stack, e.cop.car.siren = self.police_stack, True
        self.dress(e.robber)

    def dress(self, player):
        """Back in their own paint, lightbar off."""
        player.car.stack, player.car.siren = self.paint_stack(player), False

    def restore(self, players):
        for p in players:
            self.dress(p)
