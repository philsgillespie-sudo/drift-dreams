"""Uniform grid broadphase for things with a `pos`, so neighbour queries don't scan everything."""


class SpatialHash:
    def __init__(self, cell=64):
        self.cell = cell
        self.cells = {}

    def rebuild(self, items):
        cells = self.cells = {}
        c = self.cell
        for it in items:
            key = (int(it.pos.x // c), int(it.pos.y // c))
            bucket = cells.get(key)
            if bucket is None:
                cells[key] = [it]
            else:
                bucket.append(it)

    def near(self, pos, radius):
        """Everything in the cells overlapping the square of half-size `radius` round `pos`
        (a superset: callers do their own exact test)."""
        c, cells = self.cell, self.cells
        i0, i1 = int((pos[0] - radius) // c), int((pos[0] + radius) // c)
        j0, j1 = int((pos[1] - radius) // c), int((pos[1] + radius) // c)
        out = []
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                bucket = cells.get((i, j))
                if bucket:
                    out += bucket
        return out
