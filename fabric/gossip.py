"""Gossip: the Accelerator's wire + mesh-wide shadow staging (BLUEPRINT §2, §7.1, §12).

Two jobs, one anti-entropy pass:

* **Promotion push (the Accelerator).** When a capsule earns its quorum cert (Pawl+Jury →
  CANDIDATE), the author eagerly push-gossips it *as CANDIDATE, with its cert* (`GOSSIP_PUSH`). A
  receiver verifies every signature — the author's over the immutable body and each juror's ACCEPT
  over `vote_payload` — via the keyring, and only then stores it CANDIDATE locally. Gossiped state is
  never authority; gossiped *evidence* is (binding decision M4.2).

* **Mesh-wide shadow (promotion is derived, never announced).** Every node, on a live task matching a
  CANDIDATE, runs M3's `shadow_step` and appends a *signed* `SHADOW_RECORD` to its local ledger. Those
  records replicate by the same anti-entropy as capsules. A pure function — `derive_state` — flips a
  capsule ACTIVE once the local store holds ≥ `SHADOW_QUORUM_N` verified records from ≥
  `SHADOW_MIN_NODES` distinct nodes with wins ≥ `SHADOW_QUORUM_WIN` and zero invariant hits. The
  condition is monotone (records only accumulate) ⇒ no flapping; nodes converge as records replicate.
  **ACTIVE is never written to meta and never gossiped** — each node re-derives it on read.

Anti-entropy (§7.1): `digest` fingerprints a node's `(store, ledger)` over sorted add-ids ‖
tombstone-ids ‖ cert-ids ‖ shadow-record-ids; every `GOSSIP_PERIOD` peers compare digests and, on a
mismatch, exchange id sets and pull the missing records (`GOSSIP_PULL`). `reconcile` is that pull,
and it is a CRDT union: commutative, idempotent, order-independent — two divergent nodes always reach
identical digests (property-tested).

# DECISION: the `SHADOW_RECORD` OR-set (`ShadowLedger`) lives here rather than inside
# `fabric/store.py` (M4's scope lock excludes store.py). It is reconciled by the *same* anti-entropy
# pass as the capsule store — "the same anti-entropy as any other record" (decision M4.2), just
# housed beside the reconcile that carries it. A production node would fold it into one store.

# DECISION: transport is the in-process orchestrator (BLUEPRINT §13: simulated network, real
# algorithms). `build_push`/`verify_push`/`apply_push`/`reconcile` are the real gossip algorithms and
# would ride any channel; here a `GOSSIP_PUSH` is a dict handed to a peer's `receive_push`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from fabric import keyring
from fabric.capsule import Capsule, LifecycleState, check_integrity
from fabric.config import (
    QUORUM,
    SHADOW_MIN_NODES,
    SHADOW_QUORUM_N,
    SHADOW_QUORUM_WIN,
)
from fabric.jury import vote_payload
from fabric.store import Store


# --- Shadow records (mesh-wide staging evidence) --------------------------------

@dataclass(frozen=True)
class ShadowRecord:
    """One node's signed attestation of a single shadow evaluation of a CANDIDATE (decision M4.2).

    Proof-carrying: it pins the `seed` and `params`, so any node can re-run M3's `shadow_step` and
    reproduce `win`/`invariant_hits`. Promotion here requires the node's *signature* to be valid;
    re-execution is the auditor's deeper check. `record_id` is content-addressed over
    (capsule_id, node_id, seed) so re-adding the same evaluation is idempotent in the OR-set.
    """

    capsule_id: str
    node_id: str
    seed: int
    incident_class: str
    params: dict
    win: bool
    invariant_hits: int
    sim_time: float
    sig: str

    @property
    def record_id(self) -> str:
        return hashlib.sha256(
            f"{self.capsule_id}:{self.node_id}:{self.seed}".encode("utf-8")
        ).hexdigest()


def shadow_body(
    capsule_id: str,
    node_id: str,
    seed: int,
    incident_class: str,
    params: dict,
    win: bool,
    invariant_hits: int,
    sim_time: float,
) -> bytes:
    """Canonical signed bytes of a shadow record — the verification interface (sorted keys)."""
    body = {
        "capsule_id": capsule_id,
        "node_id": node_id,
        "seed": int(seed),
        "incident_class": incident_class,
        "params": params,
        "win": bool(win),
        "invariant_hits": int(invariant_hits),
        "sim_time": round(float(sim_time), 4),
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_shadow_record(
    node_id: str,
    capsule_id: str,
    seed: int,
    incident_class: str,
    params: dict,
    win: bool,
    invariant_hits: int,
    sim_time: float,
) -> ShadowRecord:
    """Seal a shadow record with the node's signature over its canonical body."""
    body = shadow_body(
        capsule_id, node_id, seed, incident_class, params, win, invariant_hits, sim_time
    )
    return ShadowRecord(
        capsule_id=capsule_id,
        node_id=node_id,
        seed=int(seed),
        incident_class=incident_class,
        params=params,
        win=bool(win),
        invariant_hits=int(invariant_hits),
        sim_time=round(float(sim_time), 4),
        sig=keyring.sign(node_id, body),
    )


def verify_shadow_record(record: ShadowRecord, node_ids: set[str] | None = None) -> bool:
    """True iff the record's author is a known mesh node and its signature checks out."""
    if node_ids is not None and record.node_id not in node_ids:
        return False
    body = shadow_body(
        record.capsule_id,
        record.node_id,
        record.seed,
        record.incident_class,
        record.params,
        record.win,
        record.invariant_hits,
        record.sim_time,
    )
    return keyring.verify(record.node_id, body, record.sig)


class ShadowLedger:
    """OR-set of shadow records, keyed by `record_id`. Content-addressed adds ⇒ idempotent; `merge`
    is a set union, the CRDT property that lets anti-entropy converge regardless of order."""

    def __init__(self) -> None:
        self.adds: dict[str, ShadowRecord] = {}

    def add(self, record: ShadowRecord) -> None:
        self.adds.setdefault(record.record_id, record)

    def ids(self) -> set[str]:
        return set(self.adds)

    def records_for(self, capsule_id: str) -> list[ShadowRecord]:
        return [r for _rid, r in sorted(self.adds.items()) if r.capsule_id == capsule_id]

    def merge(self, other: "ShadowLedger") -> "ShadowLedger":
        out = ShadowLedger()
        for rid, rec in self.adds.items():
            out.adds[rid] = rec
        for rid, rec in other.adds.items():
            out.adds.setdefault(rid, rec)
        return out

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShadowLedger):
            return NotImplemented
        return self.adds == other.adds

    def __repr__(self) -> str:
        return f"ShadowLedger(records={len(self.adds)})"


# --- Derived promotion (monotone, pure — decision M4.2) -------------------------

@dataclass(frozen=True)
class DerivedState:
    """The state a node derives locally for a capsule: `state` plus the shadow-record tally that
    produced it (so callers can surface confidence and the record/node counts)."""

    state: LifecycleState | None
    confidence: float
    records: int
    nodes: int
    wins: int
    invariant_hits: int


def derive_state(
    store: Store,
    ledger: ShadowLedger,
    capsule_id: str,
    node_ids: set[str] | None = None,
) -> DerivedState:
    """Promotion as a pure function over replicated records (binding decision M4.2).

    ACTIVE iff the local ledger holds ≥ SHADOW_QUORUM_N verified records for the capsule, from ≥
    SHADOW_MIN_NODES distinct nodes, with wins ≥ SHADOW_QUORUM_WIN and zero invariant hits. Otherwise
    the capsule reads at its meta/authored state (CANDIDATE once a cert is present). Monotone: records
    only accumulate, so a capsule never leaves ACTIVE by this function (no flapping).
    """
    verified = [r for r in ledger.records_for(capsule_id) if verify_shadow_record(r, node_ids)]
    wins = sum(1 for r in verified if r.win)
    inv = sum(r.invariant_hits for r in verified)
    nodes = len({r.node_id for r in verified})
    promoted = (
        len(verified) >= SHADOW_QUORUM_N
        and nodes >= SHADOW_MIN_NODES
        and wins >= SHADOW_QUORUM_WIN
        and inv == 0
    )
    if promoted:
        return DerivedState(
            state=LifecycleState.ACTIVE,
            confidence=round(wins / len(verified), 4),
            records=len(verified),
            nodes=nodes,
            wins=wins,
            invariant_hits=inv,
        )
    lifecycle = store.lifecycle_of(capsule_id)
    base = LifecycleState(lifecycle["state"]) if lifecycle is not None else None
    return DerivedState(
        state=base,
        confidence=0.0,
        records=len(verified),
        nodes=nodes,
        wins=wins,
        invariant_hits=inv,
    )


# --- Promotion push (GOSSIP_PUSH) ----------------------------------------------

def build_push(capsule: Capsule, quorum_cert: dict) -> dict:
    """The `GOSSIP_PUSH` payload: the capsule and the quorum cert that certifies it as CANDIDATE."""
    return {"capsule": capsule, "quorum_cert": quorum_cert}


def verify_push(push: dict, known_authors: set[str]) -> tuple[bool, str]:
    """Verify a `GOSSIP_PUSH` before trusting anything in it (decision M4.2): the capsule's content
    address and author signature, the author is a known mesh member, and every ACCEPT vote in the
    cert verifies against its juror — with ≥ QUORUM accepts. Fail-secure: any failure rejects."""
    capsule = push.get("capsule")
    cert = push.get("quorum_cert")
    if not isinstance(capsule, Capsule) or not isinstance(cert, dict):
        return False, "malformed push: missing capsule or quorum_cert"
    ok, why = check_integrity(capsule)
    if not ok:
        return False, f"push rejected: {why}"
    if capsule.provenance.author not in known_authors:
        return False, f"push rejected: author {capsule.provenance.author!r} not known to the mesh"
    partition_view = cert.get("partition_view", "")
    accepts = 0
    for vote in cert.get("votes", []):
        payload = vote_payload(
            capsule.capsule_id, vote["verdict"], vote["measured_delta"], partition_view
        )
        if not keyring.verify(vote["juror"], payload, vote["sig"]):
            return False, f"push rejected: bad juror signature from {vote['juror']!r}"
        if vote["verdict"] == "ACCEPT":
            accepts += 1
    if accepts < QUORUM:
        return False, f"push rejected: cert carries {accepts} accepts, below quorum {QUORUM}"
    return True, "ok"


def apply_push(store: Store, push: dict, sim_time: float) -> None:
    """Store a verified push as CANDIDATE locally (never ACTIVE — that is derived; decision M4.2).

    Call only after `verify_push` returns ok. Writes the capsule and a CANDIDATE lifecycle snapshot
    carrying the cert, through the store's LWW meta API.
    """
    capsule: Capsule = push["capsule"]
    cert: dict = push["quorum_cert"]
    store.add(capsule)
    lifecycle = capsule.lifecycle.model_dump(mode="json")
    lifecycle["state"] = LifecycleState.CANDIDATE.value
    lifecycle["quorum_cert"] = cert
    store.set_meta(capsule.capsule_id, lifecycle, sim_time)


# --- Anti-entropy: digest + reconcile (GOSSIP_DIGEST / GOSSIP_PULL) --------------

def _cert_ids(store: Store) -> list[str]:
    ids = []
    for cid in store.adds:
        lifecycle = store.lifecycle_of(cid)
        if lifecycle is not None and lifecycle.get("quorum_cert"):
            ids.append(cid)
    return sorted(ids)


def digest(store: Store, ledger: ShadowLedger) -> str:
    """The anti-entropy fingerprint: sha256 over sorted add-ids ‖ tombstone-ids ‖ cert-ids ‖
    shadow-record-ids. Two nodes with equal digests hold the same replicated records."""
    parts = [
        "|".join(sorted(store.adds)),
        "|".join(sorted(store.tombstones)),
        "|".join(_cert_ids(store)),
        "|".join(sorted(ledger.ids())),
    ]
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()


def _pull_store(dst: Store, src: Store) -> None:
    """Pull records `src` has that `dst` lacks (adds), plus tombstone dominance and LWW metas."""
    for cid, cap in src.adds.items():
        if cid not in dst.adds:
            dst.add(cap)
    for cid, tomb in src.tombstones.items():
        dst.tombstone(cid, tomb.sim_time, tomb.reason)
    for cid, meta in src.metas.items():
        dst.set_meta(cid, meta.lifecycle, meta.sim_time)


def _pull_ledger(dst: ShadowLedger, src: ShadowLedger) -> None:
    for rid, rec in src.adds.items():
        dst.adds.setdefault(rid, rec)


def reconcile(
    state_a: tuple[Store, ShadowLedger], state_b: tuple[Store, ShadowLedger]
) -> None:
    """One anti-entropy round between two nodes' `(store, ledger)` states.

    On a digest mismatch, each side pulls the records the other has (id-set exchange → pull). Because
    add/tombstone/meta/ledger merges are each a CRDT union, the result is order-independent and both
    states converge to an identical digest.
    """
    store_a, ledger_a = state_a
    store_b, ledger_b = state_b
    if digest(store_a, ledger_a) == digest(store_b, ledger_b):
        return
    _pull_store(store_a, store_b)
    _pull_store(store_b, store_a)
    _pull_ledger(ledger_a, ledger_b)
    _pull_ledger(ledger_b, ledger_a)
