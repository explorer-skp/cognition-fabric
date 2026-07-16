"""Excision: surgical removal of poisoned memory + the derived reputation fold (BLUEPRINT §6.4–6.5).

*Removal is surgical, not amnesiac.* A REVOKE is not a new message type — it is a signed store
record, the OR-set tombstone (binding decision M5.2), riding the exact push + anti-entropy paths
every other record rides; duplicate REVOKEs are idempotent by tombstone dominance. Excision then
computes the transitive `derived_from` closure and drops each descendant to QUARANTINED(sim_time)
meta (binding decision M5.5): the lineage must re-earn trust — re-jury at the *current* epoch on its
own evidence, then fresh shadow records — while every unrelated capsule is untouched and the
tombstoned history is retained forever (memory of the mistake is memory too).

Reputation (binding decision M5.4) follows the same doctrine as derived ACTIVE: never stored, never
messaged — a pure fold over the local replicated signed history, consumed by the existing Pawl
check 5 (below `REP_ISOLATION_FLOOR` submissions auto-reject).

All functions are pure data-in/data-out (CLAUDE.md); events go through an injected emitter.
"""

from __future__ import annotations

from dataclasses import dataclass

from agents.strategist import HeuristicStrategist, Strategist
from fabric.capsule import Capsule, LifecycleState
from fabric.config import JURY_K, QUORUM, REP_AUTHOR_SLASH, REP_JUROR_SLASH, REP_PROMOTION_CREDIT
from fabric.gossip import ShadowLedger, derive_state
from fabric.jury import JuryOutcome, juror_verdict, select_jury
from fabric.lifecycle import Emitter, _noop_emit, check_transition
from fabric.store import Store


# --- Provenance DAG -------------------------------------------------------------

def descendants(store: Store, capsule_id: str) -> list[str]:
    """Transitive closure of capsules derived (directly or through intermediaries) from
    `capsule_id`, over the local store's `provenance.derived_from` edges. Sorted, cycle-safe."""
    out: set[str] = set()
    changed = True
    while changed:
        changed = False
        for cid, capsule in store.adds.items():
            if cid in out or cid == capsule_id:
                continue
            if any(parent == capsule_id or parent in out for parent in capsule.provenance.derived_from):
                out.add(cid)
                changed = True
    return sorted(out)


# --- Excision (§6.4: REVOKE tombstone + transitive quarantine) -------------------

# DECISION: quarantine lands only on states still in play — CANDIDATE and ACTIVE (§4: "a descendant
# of a revoked capsule may be in either state when the revocation lands"). A REJECTED/EXPIRED/…
# descendant already influences nothing; re-labelling it would be a no-op transition §4 forbids.
_QUARANTINABLE = frozenset({LifecycleState.CANDIDATE, LifecycleState.ACTIVE})


@dataclass(frozen=True)
class ExcisionResult:
    """What one excision did: the tombstoned culprit, the descendants newly quarantined, and the
    one-line reason that travelled with the REVOKE."""

    culprit_id: str
    quarantined: tuple[str, ...]
    reason: str


def excise(
    store: Store,
    culprit_id: str,
    sim_time: float,
    reason: str,
    *,
    probe_alarms: tuple[str, ...] = (),
    emit: Emitter = _noop_emit,
) -> ExcisionResult:
    """Tombstone the culprit and quarantine its derived closure (binding decisions M5.2/M5.5).

    Any node may excise: the tombstone replicates via the existing anti-entropy, and duplicate
    REVOKEs converge by tombstone dominance (the store keeps the deterministic-min record). Each
    descendant still in play drops to QUARANTINED with a `quarantined_at` watermark — from then on
    only a fresh cert + fresh shadow records can re-promote it (`derive_state`). Descendants already
    quarantined or tombstoned are skipped, so re-excision writes nothing new (idempotent).
    """
    store.tombstone(culprit_id, sim_time, reason)
    emit(
        "REVOKE",
        sim_time,
        capsule_id=culprit_id,
        reason=reason,
        probe_alarms=list(probe_alarms),
    )
    quarantined: list[str] = []
    for cid in descendants(store, culprit_id):
        if store.is_tombstoned(cid):
            continue
        lifecycle = store.lifecycle_of(cid)
        if lifecycle is None:
            continue
        current = LifecycleState(lifecycle["state"])
        if current not in _QUARANTINABLE:
            continue
        check_transition(current, LifecycleState.QUARANTINED)
        lifecycle["state"] = LifecycleState.QUARANTINED.value
        lifecycle["quarantined_at"] = round(float(sim_time), 4)
        store.set_meta(cid, lifecycle, sim_time)
        quarantined.append(cid)
        emit(
            "QUARANTINE",
            sim_time,
            capsule_id=cid,
            reason=f"descendant of revoked {culprit_id[:12]} — re-jury required on own evidence",
        )
    return ExcisionResult(culprit_id=culprit_id, quarantined=tuple(quarantined), reason=reason)


# --- Reputation: a pure fold over replicated history (§6.1 check 5, §6.4 slashing) ---

def reputation(
    store: Store,
    agent_id: str,
    *,
    ledger: ShadowLedger | None = None,
    node_ids: set[str] | None = None,
) -> float:
    """Binding decision M5.4 — derived, never stored or messaged:

        1.0 + REP_PROMOTION_CREDIT · (authored capsules currently derived-ACTIVE)
            − REP_AUTHOR_SLASH     · (authored capsules tombstoned)
            − REP_JUROR_SLASH      · (ACCEPT votes signed in certs of tombstoned capsules)

    floored at 0. A threshold fact over replicated signed history — every node converges on who is
    isolated exactly as it converges on what is ACTIVE. Without a `ledger` the promotions credit is
    0 (conservative: the penalties need only the store).
    """
    promoted = revoked = signed_on_revoked = 0
    for cid, capsule in sorted(store.adds.items()):
        tombstoned = store.is_tombstoned(cid)
        if capsule.provenance.author == agent_id:
            if tombstoned:
                revoked += 1
            elif ledger is not None and derive_state(store, ledger, cid, node_ids).state == LifecycleState.ACTIVE:
                promoted += 1
        if tombstoned:
            cert = (store.lifecycle_of(cid) or {}).get("quorum_cert") or {}
            signed_on_revoked += sum(
                1
                for vote in cert.get("votes", [])
                if vote.get("juror") == agent_id and vote.get("verdict") == "ACCEPT"
            )
    rep = (
        1.0
        + REP_PROMOTION_CREDIT * promoted
        - REP_AUTHOR_SLASH * revoked
        - REP_JUROR_SLASH * signed_on_revoked
    )
    return max(0.0, round(rep, 4))


# --- Re-jury: a quarantined capsule earns its way back (§4, decision M5.5) --------

def rejury(
    capsule: Capsule,
    store: Store,
    agent_ids: list[str],
    epoch: int,
    sim_time: float,
    *,
    strategist: Strategist | None = None,
    emit: Emitter = _noop_emit,
) -> JuryOutcome:
    """Re-run the jury for a QUARANTINED capsule at the CURRENT epoch, on its own evidence only.

    The committee is re-drawn by sortition seeded with `epoch` — not the frozen `author_epoch` —
    so the original panel cannot simply reconfirm itself; the stages replay the capsule's own
    `scenario_seeds` plus each juror's private held-out, so the revoked ancestor's evidence
    contributes nothing. Quorum → CANDIDATE with a *fresh* cert; the `quarantined_at` watermark is
    preserved, so promotion still needs post-quarantine shadow records (`derive_state`). Fail-secure:
    an unexpected error rejects with `internal_error`, never admits.
    """
    lifecycle = store.lifecycle_of(capsule.capsule_id)
    if lifecycle is None or LifecycleState(lifecycle["state"]) != LifecycleState.QUARANTINED:
        raise ValueError(
            f"rejury applies only to QUARANTINED capsules; {capsule.capsule_id[:12]} is "
            f"{lifecycle['state'] if lifecycle else 'absent'}"
        )
    try:
        strategist = strategist or HeuristicStrategist()
        jurors = select_jury(agent_ids, capsule.capsule_id, epoch, capsule.provenance.author)
        verdicts = [juror_verdict(capsule, juror, agent_ids, strategist) for juror in jurors]
        accepts = sum(1 for v in verdicts if v.verdict == "ACCEPT")
        if accepts >= QUORUM:
            cert = {
                "jurors": jurors,
                "votes": [
                    {
                        "juror": v.juror,
                        "verdict": v.verdict,
                        "measured_delta": v.measured_delta,
                        "sig": v.sig,
                    }
                    for v in verdicts
                ],
                "partition_view": verdicts[0].partition_view,
                "sim_time": round(float(sim_time), 4),
            }
            outcome = JuryOutcome(
                accepted=True,
                jurors=jurors,
                verdicts=verdicts,
                quorum_cert=cert,
                reason=f"re-jury at epoch {epoch}: quorum {accepts}/{JURY_K} accept on own evidence",
            )
        else:
            first_reject = next(v for v in verdicts if v.verdict == "REJECT")
            outcome = JuryOutcome(
                accepted=False,
                jurors=jurors,
                verdicts=verdicts,
                quorum_cert=None,
                reason=f"re-jury at epoch {epoch}: quorum {accepts}/{JURY_K}: {first_reject.reason}",
            )
    except Exception as exc:  # fail-secure: never admit on an unexpected error (CLAUDE.md)
        outcome = JuryOutcome(
            accepted=False,
            jurors=[],
            verdicts=[],
            quorum_cert=None,
            reason=f"internal_error: unexpected {type(exc).__name__} during re-jury",
        )
    to = LifecycleState.CANDIDATE if outcome.accepted else LifecycleState.REJECTED
    check_transition(LifecycleState.QUARANTINED, to)
    lifecycle["state"] = to.value
    if outcome.quorum_cert is not None:
        lifecycle["quorum_cert"] = outcome.quorum_cert
    store.set_meta(capsule.capsule_id, lifecycle, sim_time)
    emit(
        "JURY_VERDICT",
        sim_time,
        capsule_id=capsule.capsule_id,
        verdict="ACCEPT" if outcome.accepted else "REJECT",
        jurors=outcome.jurors,
        reason=outcome.reason,
    )
    return outcome
