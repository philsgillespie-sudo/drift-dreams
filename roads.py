"""The road network: junctions joined by two-way roads, along the roads' centre lines.

Every district adds its own roads (District.add_roads), so traffic and "back onto the road" work
anywhere without knowing how a district is laid out. Node keys are any hashable, namespaced by the
district that made them, e.g. ("city", 3, 4).
"""
import math

from pygame.math import Vector2 as V


class RoadGraph:
    def __init__(self):
        self.nodes = {}    # key -> V, the junction's centre
        self.links = {}    # key -> [neighbour keys]
        self._edges = []   # (a, b) once per road

    def add_node(self, key, pos):
        self.nodes[key] = V(pos)
        self.links.setdefault(key, [])

    def connect(self, a, b):
        if b not in self.links[a]:
            self.links[a].append(b)
            self.links[b].append(a)
            self._edges.append((a, b))

    def pos(self, key):
        return self.nodes[key]

    def neighbours(self, key):
        return self.links[key]

    def edges(self):
        """Every road once, as (a, b)."""
        return self._edges

    def directed_edges(self):
        return self._edges + [(b, a) for a, b in self._edges]

    def nearest_point(self, p):
        """Nearest point on any road's centre line and the road's direction there (unit vector)."""
        p = V(p)
        best = None
        for a, b in self._edges:
            pa, pb = self.nodes[a], self.nodes[b]
            ab = pb - pa
            t = max(0.0, min(1.0, (p - pa).dot(ab) / ab.length_squared()))
            q = pa + ab * t
            d = q.distance_squared_to(p)
            if best is None or d < best[0]:
                best = (d, q, ab.normalize())
        return best[1], best[2]

    def edge_ahead(self, p, fwd):
        """The road (from, to) something at `p` facing `fwd` is most likely driving along:
        the nearest one running the way it faces."""
        best, best_score = None, math.inf
        for a, b in self.directed_edges():
            pa, pb = self.nodes[a], self.nodes[b]
            ab = pb - pa
            t = max(0.0, min(1.0, (p - pa).dot(ab) / ab.length_squared()))
            score = (pa + ab * t).distance_squared_to(p)
            if ab.normalize().dot(fwd) <= 0.3:
                score += 1e9              # runs the wrong way: only if nothing else will do
            if t >= 1.0:
                score += 64 ** 2          # already past this road's end
            if score < best_score:
                best, best_score = (a, b), score
        return best
