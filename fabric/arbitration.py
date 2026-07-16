"""Arbitration — deterministic capsule selection for a live task (BLUEPRINT §7, decision M4.3).

*Storage is eventually consistent. Meaning is scoped. Decisions are deterministic.* When more than
one ACTIVE capsule applies to a task, every replica must choose the same one with no coordinator — so
selection is a pure function of the replicated capsules: **priority class lexicographically →
confidence × |claimed effect| → capsule-id hash tie-break**. Same inputs everywhere ⇒ same answer,
no split-brain behavior even while stores momentarily diverge.

`applies` and `arbitrate` are pure and author-independent (CLAUDE.md); `active_matches` reads a
node's local `(store, ledger)` and derives ACTIVE via `gossip.derive_state` (promotion is derived,
never stored — decision M4.2). No Refine here: persistent-overlap sharpening is M6.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from fabric.capsule import Capsule, LifecycleState
from fabric.gossip import ShadowLedger, derive_state
from fabric.registry import context_priority_class
from fabric.store import Store
from world.taskgen import Task


def applies(capsule: Capsule, task: Task) -> bool:
    """True iff the task falls inside the capsule's declared context: class equal and every declared
    dimension contains the task's parameter (numeric interval `[lo, hi]` or categorical set — the
    same numeric-vs-set discrimination the Pawl uses for bounded contexts)."""
    if capsule.context.incident_class != task.incident_class:
        return False
    for name, declared in capsule.context.dims.items():
        value = task.params.get(name)
        if value is None:
            return False
        is_interval = (
            isinstance(declared, (list, tuple))
            and len(declared) == 2
            and all(isinstance(x, (int, float)) for x in declared)
        )
        if is_interval:
            if not (float(declared[0]) <= float(value) <= float(declared[1])):
                return False
        else:
            if value not in declared:
                return False
    return True


@dataclass(frozen=True)
class Applicable:
    """An ACTIVE capsule that matches a task, with the confidence its node derived for it."""

    capsule: Capsule
    confidence: float


def _id_hash(capsule_id: str) -> int:
    return int(hashlib.sha256(capsule_id.encode("utf-8")).hexdigest(), 16)


def arbitrate(applicables: list[Applicable]) -> Applicable | None:
    """Pick the winning capsule deterministically (decision M4.3): highest priority class
    lexicographically, then greatest `confidence × |claim.delta_pct|`, then the smaller capsule-id
    hash. Pure and author-independent — every replica returns the same winner. None if empty.

    # DECISION: priority class compared lexicographically per BLUEPRINT §7 — a COMPLIANCE-scoped
    # context (from `context_priority_class`) outranks an unscoped one (`""`), and the scheme
    # generalizes to any future label set by string order. Tie-break: the capsule whose id hashes
    # smaller wins (negate the hash so `max` selects it).
    """
    if not applicables:
        return None
    return max(
        applicables,
        key=lambda a: (
            context_priority_class(a.capsule.context.dims) or "",
            a.confidence * abs(a.capsule.claim.delta_pct),
            -_id_hash(a.capsule.capsule_id),
        ),
    )


def active_matches(
    store: Store, ledger: ShadowLedger, task: Task, node_ids: set[str] | None = None
) -> list[Applicable]:
    """Every capsule this node currently derives ACTIVE that applies to the task, with confidence.

    Reads local state only (fabric-query-before-solve): a capsule is ACTIVE iff its replicated shadow
    records clear the mesh quorum (`derive_state`), never because ACTIVE was gossiped as a fact.
    """
    matches: list[Applicable] = []
    for cid in sorted(store.live_ids()):
        capsule = store.get(cid)
        if capsule is None or not applies(capsule, task):
            continue
        derived = derive_state(store, ledger, cid, node_ids)
        if derived.state == LifecycleState.ACTIVE:
            matches.append(Applicable(capsule=capsule, confidence=derived.confidence))
    return matches
