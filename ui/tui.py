"""The rich Live dashboard (BLUEPRINT §11, milestone M7).

Everything the dashboard narrates is *derived*, never separately tracked — same discipline as
`ui/metrics.py` (M4). The panel builders below are pure functions: plain data in, a Rich renderable
out, no I/O, unit-testable without a terminal (`rich.console.Console(record=True)`). `Dashboard` is
the one place I/O happens — a thin `rich.live.Live` driver that calls `render_dashboard` on every
tick; it is not unit-tested itself, only exercised by the demo scripts behind `--tui`.

Panels (BLUEPRINT §11): Mesh · Fabric · Ratchet (per-class staircase sparklines) · Economics ·
Event log (color-coded: PAWL_BLOCK red, PROMOTED green, REVOKE/QUARANTINE magenta — Excision — REFINE
cyan, REUSE dim green). `--theme=high-contrast` (RUNBOOK failure playbook: "projector kills colors")
swaps the palette for background-backed styles that survive a washed-out projector.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rich.console import Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

Record = dict[str, Any]

# --- Event-log color palette (BLUEPRINT §11), two themes ------------------------

_EVENT_COLORS_DARK: dict[str, str] = {
    "PAWL_BLOCK": "bold red",
    "PROMOTED": "bold green",
    "REVOKE": "bold magenta",
    "QUARANTINE": "magenta",
    "REFINE": "cyan",
    "REUSE": "dim green",
    "SOLVE": "white",
    "AUTHOR": "bold blue",
    "JURY_VERDICT": "blue",
    "PROBE": "dim yellow",
    "DRIFT_ALARM": "bold yellow",
    "BISECT": "yellow",
    "PARTITION": "bold red",
    "HEAL": "bold green",
    "CRASH": "bold red",
    "RESTART": "bold green",
}

# DECISION: high-contrast pairs every style with a background so an event log stays legible on a
# washed-out projector (RUNBOOK failure playbook: "--theme=high-contrast flag, M7 requirement").
_EVENT_COLORS_HIGH_CONTRAST: dict[str, str] = {
    "PAWL_BLOCK": "bold white on red",
    "PROMOTED": "bold black on green",
    "REVOKE": "bold white on magenta",
    "QUARANTINE": "bold black on magenta",
    "REFINE": "bold black on cyan",
    "REUSE": "black on green",
    "SOLVE": "bold white on black",
    "AUTHOR": "bold white on blue",
    "JURY_VERDICT": "bold black on cyan",
    "PROBE": "black on yellow",
    "DRIFT_ALARM": "bold black on yellow",
    "BISECT": "bold white on black",
    "PARTITION": "bold white on red",
    "HEAL": "bold black on green",
    "CRASH": "bold white on red",
    "RESTART": "bold black on green",
}

THEMES = ("dark", "high-contrast")


def _event_color(event_type: str, theme: str) -> str:
    palette = _EVENT_COLORS_HIGH_CONTRAST if theme == "high-contrast" else _EVENT_COLORS_DARK
    default = "bold white on black" if theme == "high-contrast" else "white"
    return palette.get(event_type, default)


# --- Dashboard state: plain data, no live objects --------------------------------

@dataclass(frozen=True)
class DashboardState:
    """Everything one frame renders. Built by folding the event stream (`build_mesh_rows`,
    `build_fabric_rows`, and `ui.metrics`'s reducers) plus, where the fold genuinely can't reach it,
    one pure fabric query the driver already has to hand (agent reputation)."""

    sim_time: float = 0.0
    mesh: tuple[Record, ...] = ()
    fabric: tuple[Record, ...] = ()
    staircase: dict[str, list[float]] = field(default_factory=dict)
    economics: Record = field(default_factory=dict)
    event_log: tuple[Record, ...] = ()
    theme: str = "dark"
    narration: str = ""


def build_mesh_rows(records: list[Record], reputations: dict[str, float] | None = None) -> tuple[Record, ...]:
    """One row per agent: its most recent SOLVE/REUSE names the site class, the task, and whether it
    discovered or reused. Reputation is a passed-in pure fabric query (`fabric.excision.reputation`)
    — not itself derivable from the event stream, which never carries reputation as a field."""
    reputations = reputations or {}
    last: dict[str, Record] = {}
    for r in records:
        if r["type"] in ("SOLVE", "REUSE"):
            last[r["agent"]] = r
    rows = []
    for agent, r in sorted(last.items()):
        rows.append(
            {
                "agent": agent,
                "site_class": r.get("site_class", ""),
                "state": "reuse" if r["type"] == "REUSE" else "discover",
                "task_id": r.get("task_id", ""),
                "reputation": reputations.get(agent, 1.0),
            }
        )
    return tuple(rows)


# Lifecycle states a capsule can carry into the Fabric panel, in emission order.
_FABRIC_STATE_ORDER = ("SUBMITTED", "CANDIDATE", "ACTIVE", "QUARANTINED", "REVOKED", "REJECTED")


def build_fabric_rows(records: list[Record]) -> tuple[Record, ...]:
    """One row per capsule, folded from its own lifecycle events (AUTHOR → JURY_VERDICT → PROMOTED →
    REVOKE/QUARANTINE) — exactly the events the fabric already emits, nothing invented. A capsule
    with no AUTHOR event in this stream (e.g. seeded directly by a test harness) is skipped: the
    panel is a pure fold, not a store scan."""
    rows: dict[str, Record] = {}
    for r in records:
        t = r["type"]
        cid = r.get("capsule_id")
        if t == "AUTHOR":
            rows[cid] = {
                "capsule_id": cid,
                "incident_class": r.get("incident_class", ""),
                "delta_pct": r.get("delta_pct"),
                "state": "SUBMITTED",
                "confidence": None,
                "author": r.get("agent", ""),
            }
        elif cid not in rows:
            continue
        elif t == "JURY_VERDICT":
            rows[cid]["state"] = "CANDIDATE" if r.get("verdict") == "ACCEPT" else "REJECTED"
        elif t == "PROMOTED":
            rows[cid]["state"] = "ACTIVE"
            rows[cid]["confidence"] = r.get("confidence")
        elif t == "REVOKE":
            rows[cid]["state"] = "REVOKED"
        elif t == "QUARANTINE":
            rows[cid]["state"] = "QUARANTINED"
    return tuple(rows[cid] for cid in sorted(rows))


# --- Pure panel builders -----------------------------------------------------------

def mesh_table(rows: tuple[Record, ...]) -> Table:
    table = Table(title="Mesh", expand=True)
    for col in ("Agent", "Site", "State", "Reputation", "Task"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r.get("agent", "")),
            str(r.get("site_class", "")),
            str(r.get("state", "")),
            f"{r.get('reputation', 1.0):.2f}",
            str(r.get("task_id", "")),
        )
    return table


def fabric_table(rows: tuple[Record, ...]) -> Table:
    table = Table(title="Fabric", expand=True)
    for col in ("Id", "Class", "Claim", "State", "Confidence", "Author"):
        table.add_column(col)
    for r in rows:
        cid = str(r.get("capsule_id", ""))
        delta = r.get("delta_pct")
        confidence = r.get("confidence")
        table.add_row(
            cid[:10],
            str(r.get("incident_class", "")),
            f"{delta:+.1f}%" if delta is not None else "-",
            str(r.get("state", "")),
            f"{confidence:.2f}" if confidence is not None else "-",
            str(r.get("author", "")),
        )
    return table


_SPARK_BLOCKS = " ▁▂▃▄▅▆▇█"


def _sparkline(values: list[float]) -> str:
    """A best-known-cost-over-time sparkline (unicode blocks). Monotone non-increasing input (the
    staircase, BLUEPRINT §2), rendered low-to-high in block height."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = hi - lo or 1.0
    # Cheaper (lower cost) reads as a SHORTER bar — the staircase visibly steps down.
    return "".join(_SPARK_BLOCKS[min(8, int((v - lo) / span * 8))] for v in values)


def ratchet_panel(staircase: dict[str, list[float]]) -> Panel:
    """Per-class staircase sparklines of best-known cost — the money chart (BLUEPRINT §11)."""
    lines = []
    for cls in sorted(staircase):
        stairs = staircase[cls]
        if stairs:
            lines.append(f"{cls:<20} {_sparkline(stairs)}  best={stairs[-1]:.1f}")
        else:
            lines.append(f"{cls:<20} -")
    body = "\n".join(lines) if lines else "(no realized solves yet)"
    return Panel(body, title="Ratchet")


def economics_panel(summary: Record) -> Panel:
    """Cumulative cost Lane A vs Lane B, % saved, insight lead time (BLUEPRINT §11)."""
    a = summary.get("lane_a_cumulative")
    b = summary.get("lane_b_cumulative")
    pct = summary.get("pct_saved")
    lead = summary.get("median_lead_time")
    body = (
        f"Lane A (fabric ON):  {a:.1f}\n" if a is not None else "Lane A (fabric ON):  -\n"
    ) + (
        f"Lane B (fabric OFF): {b:.1f}\n" if b is not None else "Lane B (fabric OFF): -\n"
    ) + (
        f"Saved: {pct:.1f}%\n" if pct is not None else "Saved: -\n"
    ) + (
        f"Median insight lead time: {lead:.1f} sim-s" if lead is not None else "Median insight lead time: -"
    )
    return Panel(body, title="Economics")


def event_log_panel(records: tuple[Record, ...], limit: int = 12, theme: str = "dark") -> Panel:
    """The last `limit` events, color-coded by type (BLUEPRINT §11)."""
    lines = []
    for r in records[-limit:]:
        color = _event_color(r["type"], theme)
        detail = r.get("reason") or r.get("capsule_id") or ""
        lines.append(f"[{color}]{r['sim_time']:>8.2f}  {r['type']:<12} {detail}[/{color}]")
    body = "\n".join(lines) if lines else "(no events yet)"
    return Panel(body, title="Event log")


def render_dashboard(state: DashboardState) -> RenderableType:
    """The single pure function the dashboard renders — every panel folded from `state`, nothing
    else. Testable without a terminal via `rich.console.Console(record=True)`."""
    top = Table.grid(expand=True)
    top.add_column(ratio=1)
    top.add_column(ratio=1)
    top.add_row(mesh_table(state.mesh), fabric_table(state.fabric))
    bottom = Table.grid(expand=True)
    bottom.add_column(ratio=1)
    bottom.add_column(ratio=1)
    bottom.add_row(ratchet_panel(state.staircase), economics_panel(state.economics))
    header = f"sim_time={state.sim_time:.2f}"
    if state.narration:
        header = f"{header}   {state.narration}"
    return Group(
        Text(header, style="bold"),
        top,
        bottom,
        event_log_panel(state.event_log, theme=state.theme),
    )


# --- The Live driver (I/O, not unit-tested — exercised by demo scripts behind --tui) -------------

class Dashboard:
    """Thin `rich.live.Live` driver over `render_dashboard`. All decisions about *what* to render
    live in the pure functions above; this class only owns the terminal."""

    def __init__(self, theme: str = "dark") -> None:
        if theme not in THEMES:
            raise ValueError(f"unknown theme {theme!r}, expected one of {THEMES}")
        self.theme = theme
        self._live: Live | None = None

    def __enter__(self) -> "Dashboard":
        self._live = Live(
            render_dashboard(DashboardState(theme=self.theme)), refresh_per_second=8, transient=False
        )
        self._live.__enter__()
        return self

    def __exit__(self, *exc: object) -> None:
        if self._live is not None:
            self._live.__exit__(*exc)
            self._live = None

    def update(self, state: DashboardState) -> None:
        if self._live is not None:
            self._live.update(render_dashboard(state))
