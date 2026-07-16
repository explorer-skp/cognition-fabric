"""Logical simulation clock (BLUEPRINT §8: "logical time only; no wall-clock in logic").

All fabric logic reads time from a SimClock instance. Never `time.time()`; the TUI may pace
playback against wall-clock, but nothing in the decision path ever does.
"""

from __future__ import annotations


class SimClock:
    """A monotone logical clock. Time advances only when explicitly told to."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = float(start)

    @property
    def now(self) -> float:
        return self._t

    def advance(self, dt: float) -> float:
        """Advance by dt sim-seconds (dt >= 0) and return the new time."""
        if dt < 0:
            raise ValueError(f"simclock cannot advance by negative dt={dt}")
        self._t += float(dt)
        return self._t

    def set(self, t: float) -> float:
        """Jump forward to absolute time t (never backward — clock is monotone)."""
        t = float(t)
        if t < self._t:
            raise ValueError(f"simclock is monotone: cannot set {t} < now {self._t}")
        self._t = t
        return self._t
