"""A player: their car and the camera that follows them. One or two share a session."""


class Player:
    def __init__(self, index, car, camera):
        self.index = index          # 0 or 1; also the input slot that steers them
        self.car, self.camera = car, camera
        self.paint = index          # index into Game.paints

    @property
    def slot(self):
        return self.index
