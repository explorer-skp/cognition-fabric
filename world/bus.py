"""In-process async message bus (BLUEPRINT §9, §12).

A *simulated network with real algorithms on top* (§13 transport honesty): no sockets, no
wall-clock. Delivery is deterministic — messages are ordered by (sim_time, monotonically
increasing sequence number), so replaying the same publishes yields byte-identical delivery order.

Chaos hooks (partition sets, drops) are present but inert until the chaos milestone (§12: "the
chaos injector operates on the bus ... faults are network- and behavior-level only").
"""

from __future__ import annotations

import heapq
import inspect
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from world.simclock import SimClock

# BLUEPRINT §12 message set. Only TASK is exercised through M1; the rest are named here so
# the vocabulary is fixed and additive.
MESSAGE_TYPES = (
    "TASK",
    "GOSSIP_DIGEST",
    "GOSSIP_PULL",
    "GOSSIP_PUSH",
    "JURY_REQ",
    "JURY_VOTE",
    "REVOKE",
    "PROBE_REPORT",
    "HEARTBEAT",
)


@dataclass
class Message:
    """One bus message. `sig` is filled once signing exists (M2); None before then."""

    type: str
    sender: str
    sim_time: float
    payload: dict[str, Any] = field(default_factory=dict)
    sig: str | None = None


Handler = Callable[[Message], Awaitable[None] | None]


@dataclass(order=True)
class _Envelope:
    # Ordering key first (sim_time, seq); the payload is compared-excluded.
    sort_key: tuple[float, int]
    topic: str = field(compare=False)
    message: Message = field(compare=False)


class Bus:
    """Deterministic priority-ordered async bus.

    Handlers may publish further messages; anything published `at` a time >= now is delivered
    later in (time, seq) order. Same inputs → same delivery order, always.
    """

    def __init__(self, clock: SimClock) -> None:
        self._clock = clock
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._queue: list[_Envelope] = []
        self._seq = 0
        # Chaos hooks (inert until the chaos milestone). A partition is a set of frozensets of
        # reachable agents; a message from A to B is dropped if they are in different islands.
        self.partition: set[frozenset[str]] = set()
        self.dropped = 0

    def subscribe(self, topic: str, handler: Handler) -> None:
        if topic not in MESSAGE_TYPES:
            raise ValueError(f"unknown message topic: {topic!r}")
        self._subs[topic].append(handler)

    def publish(self, topic: str, message: Message, at: float | None = None) -> None:
        if topic not in MESSAGE_TYPES:
            raise ValueError(f"unknown message topic: {topic!r}")
        when = self._clock.now if at is None else float(at)
        if when < self._clock.now:
            raise ValueError(f"cannot publish into the past: at={when} < now={self._clock.now}")
        self._seq += 1
        heapq.heappush(self._queue, _Envelope((when, self._seq), topic, message))

    def _partitioned(self, sender: str, receiver: str) -> bool:
        """True if a network partition currently separates sender from receiver."""
        if not self.partition:
            return False
        for island in self.partition:
            if sender in island:
                return receiver not in island
        return False

    async def run_until_empty(self) -> int:
        """Drain the queue in deterministic order; return the count of delivered messages."""
        delivered = 0
        while self._queue:
            env = heapq.heappop(self._queue)
            when, _seq = env.sort_key
            self._clock.set(when)
            for handler in self._subs.get(env.topic, ()):
                # Partition drop is decided per subscriber identity where known; handlers that
                # do not model an identity always receive (M0/M1 have no partitions).
                result = handler(env.message)
                if inspect.isawaitable(result):
                    await result
                delivered += 1
        return delivered
