"""Chaos injection: partition, heal, node crash (BLUEPRINT §9, §12, milestone M6).

Faults are network- and behavior-level only — the chaos injector never reaches into stores (§12):
partition/heal gate *which* node pairs may anti-entropy-reconcile, and every mutation still runs
through `fabric.gossip.reconcile`, the same unit-tested CRDT merge every node already uses. Node
crash round-trips a node's store through a real `PersistentStore` (M2's crash/reload guarantee),
exactly the pattern `demo/demo_ratchet.py` (M7) proved live inside a running mesh — generalized here
into a reusable fault instead of that demo's inline copy.

# DECISION: BLUEPRINT §9 lists five faults (`poison_blatant`, `poison_subtle`, `partition`,
# `node_crash`, `flap`). This module implements `partition`/`heal`/`node_crash` — the three M6's own
# acceptance criterion needs (`tests/test_dilemma_c.py`: partition → heal → Refine). The poison
# faults are already proven end-to-end against the real pipeline in `tests/test_dilemma_b.py` (M5)
# and `demo/demo_chaos.py` (M7); `flap` (partition that toggles repeatedly) is not exercised by any
# acceptance criterion this session and is left for whoever picks up M8 polish.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass

from fabric.gossip import ShadowLedger, reconcile
from fabric.store import PersistentStore, Store


@dataclass(frozen=True)
class Partition:
    """A network partition: disjoint islands of mutually-reachable node ids. A node absent from
    every island is implicitly reachable by everyone — no partition applies to it."""

    islands: frozenset[frozenset[str]]


def partitioned(sender: str, receiver: str, partition: Partition | None) -> bool:
    """True iff `sender` cannot currently reach `receiver`. Mirrors `world.bus.Bus._partitioned`'s
    semantics, reusable off the bus since Lane A's mesh gossip bypasses the bus entirely (binding
    decision M4.2: gossip is delivered by direct verified calls, not the async bus)."""
    if partition is None:
        return False
    for island in partition.islands:
        if sender in island:
            return receiver not in island
    return False


def reconcile_within_partition(
    nodes: dict[str, tuple[Store, ShadowLedger]], partition: Partition | None
) -> None:
    """One anti-entropy round, gated by `partition`: every reachable pair reconciles (CRDT union,
    `fabric.gossip.reconcile`), every partitioned pair is skipped. `partition=None` is a full heal —
    every pair reconciles, exactly `agents.agent._all_pairs_reconcile`'s unconditional behavior.
    """
    ids = sorted(nodes)
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            if partitioned(a, b, partition) or partitioned(b, a, partition):
                continue
            reconcile(nodes[a], nodes[b])


def crash_node(store: Store) -> Store:
    """Kill a node's process and restart it: round-trip its store through a real `PersistentStore`
    (M2's crash/reload guarantee, re-asserted here) and return the reloaded copy. The unpersisted
    shadow ledger is the caller's to reset (`ShadowLedger()`) — SHADOW_RECORDs live beside the
    store, not in it (binding decision M4.2), so they do not survive a crash; the next anti-entropy
    round re-syncs them from peers, no special-cased recovery path."""
    with tempfile.TemporaryDirectory() as tmp:
        persisted = PersistentStore("crash-node", root=tmp)
        for capsule in store.adds.values():
            persisted.add(capsule)
        for cid, tomb in store.tombstones.items():
            persisted.tombstone(cid, tomb.sim_time, tomb.reason)
        for cid, meta in store.metas.items():
            persisted.set_meta(cid, meta.lifecycle, meta.sim_time)
        reloaded = PersistentStore.load("crash-node", root=tmp)
    assert reloaded.store == store, "crash/reload must be intact (M2 guarantee)"
    return reloaded.store
