"""M2 acceptance (BLUEPRINT §10): Capsule schema + signing + OR-set store + JSONL persistence.

_Accept:_ kill an agent process mid-run, restart, its store reloads intact (unit test + manual).
`test_crash_reload_roundtrip` is the executable form of that criterion; `make demo-persist` is the
manual form.
"""

from __future__ import annotations

import random

from fabric import keyring
from fabric.capsule import (
    Capsule,
    Claim,
    Context,
    Evidence,
    Lifecycle,
    LifecycleState,
    Payload,
    Provenance,
    build_capsule,
    canonical_body,
    check_integrity,
    compute_id,
)
from fabric.store import PersistentStore, Store


# --- capsule factory ---------------------------------------------------------
def make_capsule(
    *,
    author: str = "agent:site-a",
    author_epoch: int = 41,
    rate_limit_pps: int = 8000,
    state: LifecycleState = LifecycleState.SUBMITTED,
    created_at_sim: float = 132.5,
) -> Capsule:
    """A schema-valid capsule (BLUEPRINT §3 shape). Vary a field to get a distinct content address."""
    return build_capsule(
        kind="mitigation_rule",
        registry_version="3.2",
        context=Context(
            incident_class="ddos_syn_flood",
            dims={"traffic_gbps": [1.0, 10.0], "site_class": ["branch"]},
        ),
        payload=Payload(
            rule={"set": {"rate_limit_pps": rate_limit_pps, "inspection_depth": 3, "quarantine_scope": "flagged_only"}}
        ),
        claim=Claim(
            metric="solve_cost",
            baseline_median=74.0,
            with_capsule_median=22.0,
            delta_pct=-70.3,
            n_episodes=6,
        ),
        evidence=Evidence(
            scenario_seeds=[90211, 90214, 90218, 90223, 90230, 90231],
            conformance_required=["no_flagged_flow_bypasses_inspection", "quarantine_reversible"],
            trace_digest="deadbeef",
        ),
        provenance=Provenance(author=author, author_epoch=author_epoch, derived_from=[], born_of_contract=None),
        lifecycle=Lifecycle(state=state, created_at_sim=created_at_sim, ttl_sim=600.0),
    )


# --- identity & signing ------------------------------------------------------
def test_capsule_id_is_content_address_of_immutable_body():
    cap = make_capsule()
    assert cap.capsule_id == compute_id(canonical_body(cap))
    # Stable across independent constructions of the same content.
    assert make_capsule().capsule_id == cap.capsule_id


def test_capsule_id_and_sig_ignore_lifecycle():
    a = make_capsule(state=LifecycleState.SUBMITTED, created_at_sim=1.0)
    b = make_capsule(state=LifecycleState.ACTIVE, created_at_sim=999.0)
    # Only lifecycle differs → same content address and same signature.
    assert a.capsule_id == b.capsule_id
    assert a.sig == b.sig


def test_distinct_content_gives_distinct_id():
    assert make_capsule(rate_limit_pps=8000).capsule_id != make_capsule(rate_limit_pps=4000).capsule_id


def test_signature_verifies_and_tamper_is_detected():
    cap = make_capsule()
    ok, reason = check_integrity(cap)
    assert ok and reason == "ok"

    # Tamper with the immutable body (payload) without recomputing id/sig → integrity fails.
    tampered = cap.model_copy(deep=True)
    tampered.payload.rule["set"]["rate_limit_pps"] = 12000
    ok, reason = check_integrity(tampered)
    assert not ok
    assert "capsule_id mismatch" in reason


def test_forged_signature_is_rejected():
    cap = make_capsule()
    forged = cap.model_copy(deep=True)
    forged.sig = "0" * 64
    ok, reason = check_integrity(forged)
    assert not ok
    assert "bad signature" in reason


def test_keyring_is_deterministic_and_per_identity():
    body = b"canonical-body-bytes"
    assert keyring.sign("agent:site-a", body) == keyring.sign("agent:site-a", body)
    assert keyring.sign("agent:site-a", body) != keyring.sign("agent:site-b", body)
    assert keyring.verify("agent:site-a", body, keyring.sign("agent:site-a", body))
    assert not keyring.verify("agent:site-b", body, keyring.sign("agent:site-a", body))


# --- OR-set semantics --------------------------------------------------------
def test_tombstone_dominates_and_add_is_retained():
    cap = make_capsule()
    store = Store()
    store.add(cap)
    assert store.get(cap.capsule_id) is cap
    assert store.live_ids() == {cap.capsule_id}

    store.tombstone(cap.capsule_id, sim_time=200.0, reason="REVOKE: bisect culprit")
    assert store.get(cap.capsule_id) is None  # dominated
    assert store.live_ids() == set()
    assert cap.capsule_id in store.adds  # memory of the mistake retained (BLUEPRINT §4)

    # Re-adding after tombstone does not resurrect it — the tombstone is permanent.
    store.add(cap)
    assert store.get(cap.capsule_id) is None


def test_meta_is_last_writer_wins_by_sim_time():
    cap = make_capsule(state=LifecycleState.SUBMITTED)
    store = Store()
    store.add(cap)

    store.set_meta(cap.capsule_id, {"state": "CANDIDATE"}, sim_time=100.0)
    store.set_meta(cap.capsule_id, {"state": "ACTIVE"}, sim_time=300.0)
    store.set_meta(cap.capsule_id, {"state": "JURY"}, sim_time=200.0)  # older → ignored
    assert store.lifecycle_of(cap.capsule_id) == {"state": "ACTIVE"}


def test_lifecycle_of_falls_back_to_authored_lifecycle():
    cap = make_capsule(state=LifecycleState.SUBMITTED)
    store = Store()
    store.add(cap)
    assert store.lifecycle_of(cap.capsule_id)["state"] == "SUBMITTED"


# --- CRDT merge properties ---------------------------------------------------
def _random_store(rng: random.Random, pool: list[Capsule]) -> Store:
    store = Store()
    for _ in range(rng.randint(0, 6)):
        op = rng.choice(["add", "tombstone", "meta"])
        cap = rng.choice(pool)
        if op == "add":
            store.add(cap)
        elif op == "tombstone":
            store.tombstone(cap.capsule_id, sim_time=rng.uniform(0, 500), reason=f"r{rng.randint(0, 3)}")
        else:
            state = rng.choice(["JURY", "CANDIDATE", "ACTIVE", "EXPIRED"])
            store.set_meta(cap.capsule_id, {"state": state}, sim_time=rng.uniform(0, 500))
    return store


def test_merge_is_commutative_associative_idempotent():
    rng = random.Random(20260716)
    pool = [make_capsule(rate_limit_pps=p) for p in (2000, 4000, 6000, 8000, 10000)]
    for _ in range(200):
        a, b, c = (_random_store(rng, pool) for _ in range(3))
        # commutative
        assert a.merge(b) == b.merge(a)
        # associative
        assert a.merge(b).merge(c) == a.merge(b.merge(c))
        # idempotent
        assert a.merge(a) == a
        assert a.merge(b).merge(b) == a.merge(b)


# --- Acceptance: crash → reload ---------------------------------------------
def test_crash_reload_roundtrip(tmp_path):
    """Build a store, mutate it, drop the object ("crash"), reload from disk, assert full equality."""
    root = str(tmp_path)
    caps = [make_capsule(rate_limit_pps=p, state=LifecycleState.SUBMITTED) for p in (2000, 4000, 6000)]

    ps = PersistentStore("site-a", root=root)
    for cap in caps:
        ps.add(cap)
    # A lifecycle promotion (two meta updates; the later sim_time must win) and one revocation.
    ps.set_meta(caps[0].capsule_id, {"state": "CANDIDATE"}, sim_time=150.0)
    ps.set_meta(caps[0].capsule_id, {"state": "ACTIVE"}, sim_time=260.0)
    ps.tombstone(caps[2].capsule_id, sim_time=300.0, reason="REVOKE: poisoned evidence")

    # "Kill the process": drop the in-memory object entirely, reload only from the JSONL log.
    del ps
    reloaded = PersistentStore.load("site-a", root=root)

    original = PersistentStore("site-a", root=root + "_ref")
    for cap in caps:
        original.store.add(cap)
    original.store.set_meta(caps[0].capsule_id, {"state": "CANDIDATE"}, sim_time=150.0)
    original.store.set_meta(caps[0].capsule_id, {"state": "ACTIVE"}, sim_time=260.0)
    original.store.tombstone(caps[2].capsule_id, sim_time=300.0, reason="REVOKE: poisoned evidence")

    assert reloaded.store == original.store  # full equality: adds, tombstones, metas
    assert reloaded.store.get(caps[2].capsule_id) is None  # tombstone dominance survived reload
    assert reloaded.store.lifecycle_of(caps[0].capsule_id) == {"state": "ACTIVE"}  # latest lifecycle
    assert check_integrity(reloaded.store.get(caps[1].capsule_id))[0]  # capsule integrity survived


def test_crash_at_append_boundary_reloads_cleanly(tmp_path):
    """A crash mid-append leaves a truncated final line. Load must ignore it and reload the rest."""
    root = str(tmp_path)
    ps = PersistentStore("site-b", root=root)
    cap = make_capsule()
    ps.add(cap)
    ps.set_meta(cap.capsule_id, {"state": "ACTIVE"}, sim_time=100.0)

    # Simulate a partial write of a would-be next record (process killed before the newline).
    with open(ps.path, "a", encoding="utf-8") as fh:
        fh.write('{"op": "meta", "capsule_id": "abc", "life')  # no newline, truncated JSON

    reloaded = PersistentStore.load("site-b", root=root)
    assert reloaded.store.get(cap.capsule_id) is not None
    assert reloaded.store.lifecycle_of(cap.capsule_id) == {"state": "ACTIVE"}
