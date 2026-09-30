"""Opt-in kinematic intake demonstration; never publishes production refill events.

Positions are item centres in the same metre/Z-up frame as Port.center.
This models the dispenser intake animation, not force/contact physics.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Port:
    kind: str
    center: tuple
    axis: tuple
    tolerance: tuple
    depth: float = 0.20
    duration: float = 1.0
    dwell: float = 0.25
    angle_limit: float = math.radians(10)
    max_speed: float = 0.03

    def __post_init__(self):
        if any(len(v) != 3 for v in (self.center, self.axis, self.tolerance)):
            raise ValueError('port vectors must have three values')
        values = (*self.center, *self.axis, *self.tolerance, self.depth,
                  self.duration, self.dwell, self.angle_limit, self.max_speed)
        if not all(math.isfinite(v) for v in values):
            raise ValueError('non-finite port')
        if abs(math.sqrt(sum(v*v for v in self.axis)) - 1) > 1e-6:
            raise ValueError('axis must be normalized')
        if min(*self.tolerance, self.depth, self.duration) <= 0 or min(
                self.dwell, self.angle_limit, self.max_speed) < 0:
            raise ValueError('invalid capture limits')


class Intake:
    """One-item port. Caller must provide observed release, angle and speed.

    Reset clears candidates and motion, but preserves accepted IDs to avoid
    double-counting an item. A new demo instance starts a fresh inventory.
    """

    def __init__(self, port):
        self.port = port
        self.accepted = set()
        self.last_time = None
        self.pending = None
        self.active = None

    def reset(self):
        self.pending = None
        self.active = None
        self.last_time = None

    def _clock(self, now):
        if not math.isfinite(now) or (self.last_time is not None and now < self.last_time):
            raise ValueError('time must be finite and monotonic; reset before replay')
        self.last_time = now

    def offer(self, now, item_id, kind, position, *, held, angle, speed):
        self._clock(now)
        if self.active:
            return 'busy'
        if item_id in self.accepted:
            return 'already_stored'
        if len(position) != 3 or not all(math.isfinite(v) for v in (*position, angle, speed)):
            self.pending = None
            return 'invalid_sample'
        reason = ('wrong_kind' if kind != self.port.kind else
                  'held' if held else
                  'misaligned' if abs(angle) > self.port.angle_limit else
                  'moving' if abs(speed) > self.port.max_speed else
                  'outside' if any(abs(a-b) > t for a, b, t in zip(
                      position, self.port.center, self.port.tolerance, strict=True)) else None)
        if reason:
            self.pending = None
            return reason
        if self.pending is None or self.pending[0] != item_id:
            self.pending = (item_id, now)
        if now - self.pending[1] + 1e-9 < self.port.dwell:
            return 'settling'
        self.active = (item_id, now, tuple(position))
        self.pending = None
        return 'capture_started'

    def advance(self, now):
        self._clock(now)
        if not self.active:
            return None
        item_id, started, start = self.active
        t = min(1., max(0., (now-started)/self.port.duration))
        u = t*t*(3-2*t)
        # Centre gently while drawing the item along the intake axis.
        end = tuple(c+a*self.port.depth for c, a in zip(self.port.center, self.port.axis, strict=True))
        point = tuple(a+(b-a)*u for a, b in zip(start, end, strict=True))
        complete = t >= 1
        if complete:
            self.accepted.add(item_id)
            self.active = None
        return {'item_id': item_id, 'position': point, 'complete': complete}
