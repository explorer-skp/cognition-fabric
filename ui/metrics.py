"""Fabric metrics — a pure reducer over the event stream (BLUEPRINT §11, decision M4.5).

Everything the dashboard narrates is *derived*, never separately tracked: the ratchet staircase, the
reuse-vs-discovery gap, insight lead time, and the twin-lane cumulative cost are all folded out of
the one JSONL event stream. The TUI (M7) only renders what these functions return; keeping them pure
means the demo's headline numbers are reproducible and unit-testable (CLAUDE.md).

A "realized solve" is any SOLVE (discovery) or REUSE (from memory) event — both carry `solve_cost`
and `incident_class`; REUSE additionally carries the `capsule_id` it reused.
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any

Record = dict[str, Any]

_REALIZED = ("SOLVE", "REUSE")


def _realized(records: list[Record]) -> list[Record]:
    return [r for r in records if r["type"] in _REALIZED]


def cumulative_cost(records: list[Record]) -> float:
    """Total realized solve cost across the run (discovery + reuse) — one lane's economics."""
    return round(sum(r["solve_cost"] for r in _realized(records)), 4)


def ratchet_staircase(records: list[Record]) -> dict[str, list[float]]:
    """Per incident class, the best-known realized solve cost *so far* over the ordered stream.

    Monotone non-increasing by construction (a running minimum) — the ratchet only turns one way.
    The staircase steps down the first time reuse beats the standing discovery best (BLUEPRINT §2).
    """
    best: dict[str, float] = {}
    stairs: dict[str, list[float]] = defaultdict(list)
    for r in _realized(records):
        cls = r["incident_class"]
        cost = r["solve_cost"]
        best[cls] = cost if cls not in best else min(best[cls], cost)
        stairs[cls].append(best[cls])
    return dict(stairs)


def reuse_vs_discovery(records: list[Record]) -> dict[str, dict]:
    """Per-class and overall medians of discovery (SOLVE) vs reuse (REUSE) cost, with counts.

    `ratio` is reuse_median / discovery_median where both exist — the ratchet's headline: reuse
    should land well below half of discovery once a class has memory.
    """
    disc: dict[str, list[float]] = defaultdict(list)
    reuse: dict[str, list[float]] = defaultdict(list)
    for r in records:
        if r["type"] == "SOLVE":
            disc[r["incident_class"]].append(r["solve_cost"])
        elif r["type"] == "REUSE":
            reuse[r["incident_class"]].append(r["solve_cost"])

    def block(d: list[float], u: list[float]) -> dict:
        out: dict[str, Any] = {
            "discovery_n": len(d),
            "reuse_n": len(u),
            "discovery_median": round(median(d), 4) if d else None,
            "reuse_median": round(median(u), 4) if u else None,
        }
        if d and u:
            out["ratio"] = round(median(u) / median(d), 4)
        return out

    result = {
        cls: block(disc.get(cls, []), reuse.get(cls, []))
        for cls in sorted(set(disc) | set(reuse))
    }
    all_disc = [c for costs in disc.values() for c in costs]
    all_reuse = [c for costs in reuse.values() for c in costs]
    result["overall"] = block(all_disc, all_reuse)
    return result


def insight_lead_times(records: list[Record]) -> dict[str, float]:
    """Per capsule, sim-time from AUTHOR to the *last* node that locally derives it ACTIVE (the
    Accelerator's latency, BLUEPRINT §2). Only capsules that reached ACTIVE somewhere appear."""
    authored_at: dict[str, float] = {}
    last_active: dict[str, float] = {}
    for r in records:
        if r["type"] == "AUTHOR":
            cid = r["capsule_id"]
            authored_at[cid] = min(authored_at.get(cid, r["sim_time"]), r["sim_time"])
        elif r["type"] == "PROMOTED":
            cid = r["capsule_id"]
            last_active[cid] = max(last_active.get(cid, r["sim_time"]), r["sim_time"])
    return {
        cid: round(last_active[cid] - authored_at[cid], 4)
        for cid in sorted(last_active)
        if cid in authored_at
    }


def reuse_sites(records: list[Record]) -> dict[str, set[str]]:
    """Per reused capsule_id, the set of agents that reused it — the propagation footprint."""
    sites: dict[str, set[str]] = defaultdict(set)
    for r in records:
        if r["type"] == "REUSE":
            sites[r["capsule_id"]].add(r["agent"])
    return dict(sites)


def non_author_reuse_sites(records: list[Record]) -> set[str]:
    """Distinct agents that reused a capsule they did NOT author — the network-effect evidence
    (repeat incidents solved cheaply at *other* sites, BLUEPRINT §10 M4 acceptance)."""
    author_of: dict[str, str] = {
        r["capsule_id"]: r["agent"] for r in records if r["type"] == "AUTHOR"
    }
    out: set[str] = set()
    for capsule_id, sites in reuse_sites(records).items():
        out |= {a for a in sites if a != author_of.get(capsule_id)}
    return out


def summarize(records_a: list[Record], records_b: list[Record]) -> dict:
    """The compact twin-lane summary the demo prints and the TUI (M7) renders."""
    cum_a = cumulative_cost(records_a)
    cum_b = cumulative_cost(records_b)
    pct_saved = round(100.0 * (cum_b - cum_a) / cum_b, 2) if cum_b else 0.0
    leads = insight_lead_times(records_a)
    return {
        "lane_a_cumulative": cum_a,
        "lane_b_cumulative": cum_b,
        "pct_saved": pct_saved,
        "reuse_vs_discovery": reuse_vs_discovery(records_a),
        "staircase": ratchet_staircase(records_a),
        "insight_lead_times": leads,
        "median_lead_time": round(median(leads.values()), 4) if leads else None,
        "non_author_reuse_sites": sorted(non_author_reuse_sites(records_a)),
        "promotions": sum(1 for r in records_a if r["type"] == "PROMOTED"),
        "authored": sum(1 for r in records_a if r["type"] == "AUTHOR"),
    }
