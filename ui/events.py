"""The single structured event stream (BLUEPRINT §9, CLAUDE.md: "one structured JSONL stream").

Everything the fabric does is emitted here as one ordered JSONL stream; the TUI (from M7) is a pure
consumer. Deterministic by construction: records carry logical `sim_time`, never wall-clock, and are
serialized with sorted keys so the same run yields byte-identical output.
"""

from __future__ import annotations

import json
from typing import Any, TextIO

# Event types (CLAUDE.md). The vocabulary is fixed; milestones add emitters, never rename types.
EVENT_TYPES = (
    "TASK",
    "SOLVE",
    "AUTHOR",
    "PAWL_BLOCK",
    "JURY_VERDICT",
    "PROMOTED",
    "REUSE",
    "REVOKE",
    "QUARANTINE",
    "PROBE",
    "DRIFT_ALARM",
    "BISECT",
    "REFINE",
    "PARTITION",
    "HEAL",
    "CRASH",
    "RESTART",
)


class EventStream:
    """Append-only structured event sink. In-memory always; optionally mirrored to a JSONL file."""

    def __init__(self, path: str | None = None) -> None:
        self._records: list[dict[str, Any]] = []
        self._fh: TextIO | None = open(path, "w", encoding="utf-8") if path else None

    def emit(self, event_type: str, sim_time: float, **fields: Any) -> dict[str, Any]:
        if event_type not in EVENT_TYPES:
            raise ValueError(f"unknown event type: {event_type!r}")
        record = {"type": event_type, "sim_time": round(float(sim_time), 4), **fields}
        self._records.append(record)
        if self._fh is not None:
            self._fh.write(json.dumps(record, sort_keys=True) + "\n")
            self._fh.flush()
        return record

    def records(self) -> list[dict[str, Any]]:
        return list(self._records)

    def of_type(self, event_type: str) -> list[dict[str, Any]]:
        return [r for r in self._records if r["type"] == event_type]

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "EventStream":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
