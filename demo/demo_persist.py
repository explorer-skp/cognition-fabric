"""Manual check for M2 persistence (BLUEPRINT §10 accept: "unit test + manual").

Builds a node's PersistentStore, adds capsules, promotes one via lifecycle metadata, revokes another
(tombstone), then "crashes" (drops the object) and reloads purely from the on-disk JSONL log —
printing before/after so a human can eyeball that adds, tombstone dominance, and the latest lifecycle
all survive the restart. Runs under a scratch `.state/_demo_persist` root; wipe with `make clean-state`.
"""

from __future__ import annotations

from fabric.capsule import Lifecycle, LifecycleState, build_capsule
from fabric.capsule import Claim, Context, Evidence, Payload, Provenance
from fabric.store import PersistentStore

ROOT = ".state/_demo_persist"


def _capsule(rate_limit_pps: int, author: str = "agent:site-a"):
    return build_capsule(
        kind="mitigation_rule",
        registry_version="3.2",
        context=Context(incident_class="ddos_syn_flood", dims={"traffic_gbps": [1.0, 10.0], "site_class": ["branch"]}),
        payload=Payload(rule={"set": {"rate_limit_pps": rate_limit_pps, "inspection_depth": 3, "quarantine_scope": "flagged_only"}}),
        claim=Claim(metric="solve_cost", baseline_median=74.0, with_capsule_median=22.0, delta_pct=-70.3, n_episodes=6),
        evidence=Evidence(scenario_seeds=[90211, 90214, 90218, 90223], conformance_required=["quarantine_reversible"], trace_digest="deadbeef"),
        provenance=Provenance(author=author, author_epoch=41, derived_from=[], born_of_contract=None),
        lifecycle=Lifecycle(state=LifecycleState.SUBMITTED, created_at_sim=100.0, ttl_sim=600.0),
    )


def _dump(label: str, store) -> None:
    print(f"# {label}: {store!r}")
    for cid in sorted(store.adds):
        live = "LIVE " if cid in store.live_ids() else "TOMB "
        state = store.lifecycle_of(cid)["state"]
        print(f"    {live}{cid[:12]}  state={state}")


def main() -> None:
    import shutil

    shutil.rmtree(ROOT, ignore_errors=True)  # deterministic manual run

    print("# demo-persist (M2): a node store survives a crash + restart")
    ps = PersistentStore("site-a", root=ROOT)
    caps = [_capsule(p) for p in (4000, 8000, 12000)]
    for cap in caps:
        ps.add(cap)
    # Promote the first capsule (SUBMITTED → CANDIDATE → ACTIVE) and revoke the third.
    ps.set_meta(caps[0].capsule_id, {"state": "CANDIDATE"}, sim_time=150.0)
    ps.set_meta(caps[0].capsule_id, {"state": "ACTIVE"}, sim_time=260.0)
    ps.tombstone(caps[2].capsule_id, sim_time=300.0, reason="REVOKE: poisoned evidence")
    _dump("before crash", ps.store)

    print("# --- process killed (in-memory store dropped); reloading from .state log ---")
    del ps
    reloaded = PersistentStore.load("site-a", root=ROOT)
    _dump("after reload", reloaded.store)

    assert reloaded.store.get(caps[2].capsule_id) is None, "tombstone must survive reload"
    assert reloaded.store.lifecycle_of(caps[0].capsule_id) == {"state": "ACTIVE"}, "latest lifecycle must survive"
    print("# OK: adds, tombstone dominance, and latest lifecycle all reloaded intact.")


if __name__ == "__main__":
    main()
