"""Capsule lifecycle: the §4 state machine, the submit pipeline, and shadow staging (BLUEPRINT §4, §5).

This module wires the pure pieces together: `submit()` drives SUBMITTED → Pawl → Jury → CANDIDATE,
and the shadow harness drives CANDIDATE → ACTIVE | REJECTED. State and the quorum certificate are
*lifecycle metadata*, written through the M2 store API (`set_meta`) — never into the hashed
immutable body (binding decision M3.4).

Shadow staging (§5.7, binding decision M3.5): as CANDIDATE, a capsule influences nothing; on each
applicable task the harness forks the seeded episode and runs both branches through the one solve
path (decision M3.1), recording win/loss and invariant hits. Promotion needs ≥ SHADOW_WIN of
SHADOW_N wins with zero invariant hits; `confidence = wins / SHADOW_N`. This is a simulator —
forking a seeded episode is free, which is why staging costs nothing to run. Live agent-loop wiring
and capsule authoring are M4 (`agents/agent.py` is untouched here).

Events (PAWL_BLOCK, JURY_VERDICT, PROMOTED) go through an injected `emit(event_type, sim_time,
**fields)` callable defaulting to a no-op — the signature matches `ui.events.EventStream.emit`, so
callers pass `stream.emit`; there is no global state and tests stay silent (binding decision M3.6).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # typing only — the runtime import stays lazy (see submit)
    from fabric.gossip import ShadowLedger

from agents.strategist import HeuristicStrategist, Strategist
from fabric.capsule import Capsule, LifecycleState
from fabric.config import SHADOW_N, SHADOW_WIN
from fabric.jury import metric_value, validate_capsule
from fabric.pawl import PawlContext, pawl_check
from fabric.store import Store
from world.taskgen import Task

Emitter = Callable[..., object]


def _noop_emit(event_type: str, sim_time: float, **fields: object) -> None:
    return None


# --- State machine (§4) ---------------------------------------------------------

# Legal transitions, verbatim from the §4 diagram. REVOKED and EXPIRED are terminal for the
# capsule's influence (a REVOKED id lives on as an OR-set tombstone, M5's job to write).
# DECISION: QUARANTINED is reachable from both CANDIDATE and ACTIVE — a descendant of a revoked
# capsule may be in either state when the revocation lands.
LEGAL_TRANSITIONS: dict[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.DRAFT: frozenset({LifecycleState.SUBMITTED}),
    LifecycleState.SUBMITTED: frozenset({LifecycleState.JURY, LifecycleState.REJECTED}),
    LifecycleState.JURY: frozenset({LifecycleState.CANDIDATE, LifecycleState.REJECTED}),
    LifecycleState.CANDIDATE: frozenset(
        {LifecycleState.ACTIVE, LifecycleState.REJECTED, LifecycleState.QUARANTINED}
    ),
    LifecycleState.ACTIVE: frozenset(
        {
            LifecycleState.SUPERSEDED,
            LifecycleState.EXPIRED,
            LifecycleState.REVOKED,
            LifecycleState.QUARANTINED,
        }
    ),
    LifecycleState.QUARANTINED: frozenset({LifecycleState.CANDIDATE, LifecycleState.REJECTED}),
    LifecycleState.REJECTED: frozenset(),
    LifecycleState.SUPERSEDED: frozenset(),
    LifecycleState.EXPIRED: frozenset(),
    LifecycleState.REVOKED: frozenset(),
}


def check_transition(current: LifecycleState, to: LifecycleState) -> None:
    """Guard every state write: an illegal transition is a programming error, not a policy call —
    raise rather than silently corrupt the lifecycle (fail-secure)."""
    if to not in LEGAL_TRANSITIONS[current]:
        raise ValueError(f"illegal lifecycle transition {current.value} → {to.value}")


def _write_state(
    store: Store,
    capsule: Capsule,
    to: LifecycleState,
    sim_time: float,
    *,
    quorum_cert: dict | None = None,
    confidence: float | None = None,
) -> dict:
    """Advance a capsule's lifecycle metadata through the store (never the hashed body).

    # DECISION: the store's meta merge is LWW by sim_time with a deterministic JSON tie-break
    # (M2), so two state writes at the *same* sim_time race the tie-break. Callers therefore write
    # at most one snapshot per sim tick: `submit` validates every logical transition but persists
    # only the pipeline's outcome; the shadow harness writes its outcome at a later tick.
    """
    lifecycle = store.lifecycle_of(capsule.capsule_id)
    if lifecycle is None:
        raise ValueError(f"capsule {capsule.capsule_id[:12]} not in store — add before transitioning")
    check_transition(LifecycleState(lifecycle["state"]), to)
    lifecycle["state"] = to.value
    if quorum_cert is not None:
        lifecycle["quorum_cert"] = quorum_cert
    if confidence is not None:
        lifecycle["confidence"] = round(confidence, 4)
    store.set_meta(capsule.capsule_id, lifecycle, sim_time)
    return lifecycle


# --- Partition semantics: provisional-cert demotion on heal (BLUEPRINT §7.5, milestone M6) -------

def provisional_cert_demotion(quorum_cert: dict | None, mesh_size: int) -> bool:
    """True iff a cert was formed with too small a `partition_view` to be trusted mesh-wide (§7.5):
    `|partition_view| < ceil((N+1)/2)`, i.e. the jury did not see a majority of the mesh. A cert
    with no `partition_view` (or no cert at all) never demotes — that is the pre-M6, full-mesh case.
    Pure: reads the cert dict, no I/O."""
    if not quorum_cert:
        return False
    view = quorum_cert.get("partition_view") or ""
    seen = len([a for a in view.split("|") if a])
    majority = -(-(mesh_size + 1) // 2)  # ceil((N+1)/2) via integer ceiling division
    return seen < majority


def demote_provisional(store: Store, capsule: Capsule, sim_time: float, *, emit: Emitter = _noop_emit) -> dict:
    """Demote an ACTIVE capsule formed on a minority-island cert (§7.5): its knowledge is preserved
    (still in the store, still gossiped) but no longer authoritative until it re-earns promotion on
    fresh, mesh-wide evidence.

    # DECISION: lands on QUARANTINED, not a new ACTIVE→CANDIDATE edge — `tests/test_m3_pipeline.py`
    # already locks ACTIVE→CANDIDATE as illegal (CLAUDE.md: never modify an existing test), and
    # QUARANTINED already means exactly this ("not currently trusted, must re-earn it") for
    # Excision's descendants (M5). Reusing it here is not a second meaning bolted on — a minority-
    # island cert and a poisoned ancestor are both "the evidence behind this promotion doesn't hold
    # up," and `derive_state`'s `quarantined_at` watermark (fabric/gossip.py, M5) already refuses to
    # count pre-watermark shadow records or a pre-watermark cert, so the exact same re-promotion
    # machinery — fresh cert + fresh mesh-wide records — applies with no gossip.py change needed.
    """
    lifecycle = store.lifecycle_of(capsule.capsule_id)
    if lifecycle is None:
        raise ValueError(f"capsule {capsule.capsule_id[:12]} not in store — add before transitioning")
    check_transition(LifecycleState(lifecycle["state"]), LifecycleState.QUARANTINED)
    lifecycle["state"] = LifecycleState.QUARANTINED.value
    lifecycle["quarantined_at"] = round(float(sim_time), 4)
    store.set_meta(capsule.capsule_id, lifecycle, sim_time)
    emit(
        "HEAL",
        sim_time,
        capsule_id=capsule.capsule_id,
        reason="provisional-cert demotion: partition_view below mesh majority at cert time — "
               "quarantined pending re-jury and fresh mesh-wide evidence on heal",
    )
    return lifecycle


# --- Submission pipeline: SUBMITTED → Pawl → Jury → CANDIDATE (§5.1–§5.6) --------

def submit(
    capsule: Capsule,
    store: Store,
    agent_ids: list[str],
    sim_time: float,
    *,
    pawl_ctx: PawlContext | None = None,
    strategist: Strategist | None = None,
    emit: Emitter = _noop_emit,
    ledger: "ShadowLedger | None" = None,
    node_ids: set[str] | None = None,
    partition_view: str | None = None,
) -> tuple[LifecycleState, str]:
    """Run one capsule through admission. Returns the resulting state and the pipeline's one-line
    reason (the same string the PAWL_BLOCK / JURY_VERDICT event carries).

    Every logical §4 transition is validated (DRAFT → SUBMITTED → Pawl → JURY → …), but only the
    pipeline's *outcome* is persisted — one meta snapshot per sim tick (see `_write_state`).

    `partition_view` (milestone M6): the reachable-agent view if the jury convenes during a
    partition; `None` means the full mesh (unchanged M3-M5 behavior) — see `validate_capsule`."""
    if pawl_ctx is None:
        # DECISION (M5.4 wiring): with no caller-supplied Pawl context, derive the author's
        # reputation as the pure fold over this node's replicated history (fabric/excision.py) —
        # reputation is never stored or messaged, so isolation is a derived threshold fact exactly
        # like ACTIVE. Lazy import: excision consumes this module's transition guard.
        from fabric.excision import reputation

        pawl_ctx = PawlContext(
            reputation=reputation(
                store, capsule.provenance.author, ledger=ledger, node_ids=node_ids
            )
        )
    store.add(capsule)
    lifecycle = store.lifecycle_of(capsule.capsule_id)
    state = LifecycleState(lifecycle["state"])
    if state == LifecycleState.DRAFT:
        check_transition(state, LifecycleState.SUBMITTED)
        state = LifecycleState.SUBMITTED

    def settle(to: LifecycleState, *, quorum_cert: dict | None = None) -> None:
        check_transition(state, to)
        lifecycle["state"] = to.value
        if quorum_cert is not None:
            lifecycle["quorum_cert"] = quorum_cert
        store.set_meta(capsule.capsule_id, lifecycle, sim_time)

    result = pawl_check(capsule, pawl_ctx)
    if not result.ok:
        settle(LifecycleState.REJECTED)
        emit(
            "PAWL_BLOCK",
            sim_time,
            capsule_id=capsule.capsule_id,
            author=capsule.provenance.author,
            reason=result.reason,
        )
        return LifecycleState.REJECTED, result.reason

    check_transition(state, LifecycleState.JURY)
    state = LifecycleState.JURY
    outcome = validate_capsule(
        capsule, agent_ids, strategist=strategist, sim_time=sim_time, partition_view=partition_view
    )
    emit(
        "JURY_VERDICT",
        sim_time,
        capsule_id=capsule.capsule_id,
        verdict="ACCEPT" if outcome.accepted else "REJECT",
        jurors=outcome.jurors,
        reason=outcome.reason,
    )
    if not outcome.accepted:
        settle(LifecycleState.REJECTED)
        return LifecycleState.REJECTED, outcome.reason

    settle(LifecycleState.CANDIDATE, quorum_cert=outcome.quorum_cert)
    return LifecycleState.CANDIDATE, outcome.reason


# --- Shadow staging: CANDIDATE → ACTIVE | REJECTED (§5.7, decision M3.5) ----------

@dataclass(frozen=True)
class ShadowTracker:
    """Running tally of a CANDIDATE's shadow evaluation. Immutable — each step returns a new one."""

    steps: int = 0
    wins: int = 0
    invariant_hits: int = 0


def shadow_step(
    capsule: Capsule, task: Task, strategist: Strategist, tracker: ShadowTracker
) -> ShadowTracker:
    """One shadow evaluation: fork the task's seeded episode in the simulated world and run both
    branches through the one solve path (decision M3.1) — the CANDIDATE influences nothing.

    # DECISION: shadow win/loss is judged on solve_cost (the fabric's headline KPI) regardless of
    # the capsule's claim metric — staging protects the *system*, not the claim. A tie is a loss
    # (deterministic, and a capsule that changes nothing has no business being promoted).
    """
    without = strategist.solve(task, prior=None)
    with_capsule = strategist.solve(task, prior=dict(capsule.payload.rule))
    win = metric_value(with_capsule, "solve_cost") < metric_value(without, "solve_cost")
    return replace(
        tracker,
        steps=tracker.steps + 1,
        wins=tracker.wins + (1 if win else 0),
        invariant_hits=tracker.invariant_hits + with_capsule.metrics.invariant_hits,
    )


def shadow_verdict(tracker: ShadowTracker) -> tuple[bool, float, str]:
    """The promotion decision after SHADOW_N steps: (promote, confidence, reason)."""
    if tracker.steps < SHADOW_N:
        raise ValueError(f"shadow verdict needs {SHADOW_N} steps, have {tracker.steps}")
    confidence = tracker.wins / SHADOW_N
    if tracker.invariant_hits > 0:
        return (
            False,
            confidence,
            f"shadow staging: {tracker.invariant_hits} invariant hit(s) across {SHADOW_N} "
            f"shadow episodes — zero tolerance",
        )
    if tracker.wins < SHADOW_WIN:
        return (
            False,
            confidence,
            f"shadow staging: won {tracker.wins}/{SHADOW_N} shadow episodes, "
            f"below promotion threshold {SHADOW_WIN}",
        )
    return (
        True,
        confidence,
        f"shadow staging: won {tracker.wins}/{SHADOW_N} shadow episodes with zero invariant hits",
    )


def run_shadow(
    capsule: Capsule,
    tasks: list[Task],
    store: Store,
    sim_time: float,
    *,
    strategist: Strategist | None = None,
    emit: Emitter = _noop_emit,
) -> tuple[LifecycleState, ShadowTracker, str]:
    """Evaluate a CANDIDATE over its next SHADOW_N applicable tasks, then promote or reject."""
    if len(tasks) < SHADOW_N:
        raise ValueError(f"shadow staging needs {SHADOW_N} applicable tasks, got {len(tasks)}")
    strategist = strategist or HeuristicStrategist()
    tracker = ShadowTracker()
    for task in tasks[:SHADOW_N]:
        tracker = shadow_step(capsule, task, strategist, tracker)
    promote, confidence, reason = shadow_verdict(tracker)
    if promote:
        _write_state(store, capsule, LifecycleState.ACTIVE, sim_time, confidence=confidence)
        emit(
            "PROMOTED",
            sim_time,
            capsule_id=capsule.capsule_id,
            confidence=round(confidence, 4),
            reason=reason,
        )
        return LifecycleState.ACTIVE, tracker, reason
    _write_state(store, capsule, LifecycleState.REJECTED, sim_time)
    return LifecycleState.REJECTED, tracker, reason
