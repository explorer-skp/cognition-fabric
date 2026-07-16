"""Dilemma B — Drift & Poisoning, in one sentence: admission validates the claim, Sentinels
validate the system — subtle poison that honestly passes the border is flagged by a probe within
one period, bisected to the exact culprits, and excised surgically (tombstone + transitive
quarantine), never amnesically.

The poisons are built exactly per BLUEPRINT §6.5 and binding decision M5.6: they pass the GENUINE
admission pipeline — real Pawl, real jury quorum, real mesh shadow records earned by `shadow_step`
replays on two nodes — because their `solve_cost` claims are honestly measured (cheap-reuse
attempts savings dominate). The harm is off-claim: anchored one refinement-basin below the traffic
optimum, the 3-attempt reuse budget cannot escape, and `fp_quarantines` regresses on in-context
golden scenarios that clean solves handle with zero false positives. The rogue (`agent:site-e`)
authors two such poisons, so the excise → re-probe loop runs two genuine passes and the reputation
fold lands at 1.0 − 2×0.4 = 0.2 < 0.3 — organic isolation.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from functools import lru_cache

from agents.agent import FabricAgent
from agents.strategist import HeuristicStrategist
from fabric.capsule import Capsule, LifecycleState
from fabric.config import PROBE_PERIOD, REP_ISOLATION_FLOOR, REP_JUROR_SLASH, REP_PROMOTION_CREDIT
from fabric.excision import ExcisionResult, excise, rejury, reputation
from fabric.gossip import ShadowLedger, derive_state, reconcile, sign_shadow_record
from fabric.jury import JuryOutcome, select_jury
from fabric.lifecycle import ShadowTracker, shadow_step, submit
from fabric.probes import BisectStep, ProbeReport, Sentinel, bisect_culprit, probe, suspects
from fabric.store import Store
from tests.test_dilemma_a import AGENT_IDS, author_measure, make_capsule
from ui.events import EventStream
from world.taskgen import Task

STRATEGIST = HeuristicStrategist()
NODE_IDS = set(AGENT_IDS)
ROGUE = "agent:site-e"
ALL_SITES = ["branch", "campus", "dc"]

# The two subtle poisons (prototype-verified per decision M5.6): honest −44%/−46% solve_cost
# medians at the jury, fp regression on in-context goldens under the 3-attempt reuse budget.
P1_RULE = {"rate_limit_pps": 4000, "inspection_depth": 3}
P1_DIMS = {"traffic_gbps": [4.0, 9.0], "site_class": ALL_SITES}
P2_RULE = {"rate_limit_pps": 6000, "inspection_depth": 3}
P2_DIMS = {"traffic_gbps": [6.5, 11.0], "site_class": ALL_SITES}


def _measured(incident_class: str, dims: dict, rule: dict, seeds: list[int], author: str) -> Capsule:
    """An honestly measured capsule: the claim is replayed through the jury's own path, never invented."""
    episodes = [author_measure(incident_class, dims, rule, "solve_cost", s) for s in seeds]
    median = statistics.median(e.delta_pct for e in episodes)
    return make_capsule(
        incident_class=incident_class, dims=dims, rule=rule, metric="solve_cost",
        seeds=list(seeds), delta_pct=round(median, 1), author=author,
    )


def _task(incident_class: str, site: str, seed: int, **params: object) -> Task:
    return Task(
        task_id=f"live-{seed}",
        incident_class=incident_class,
        site_class=site,
        params={"incident_class": incident_class, "site_class": site, **params},
        arrival_sim=0.0,
        seed=seed,
    )


def _mesh_shadow(store: Store, ledger: ShadowLedger, capsule: Capsule, tasks: list[Task],
                 nodes: tuple[str, ...], sim_time: float) -> None:
    """REAL mesh shadow (decision M5.6 — no stuffed wins): each node forks the seeded episode via
    `shadow_step` (both branches through the one solve path) and signs the honest outcome."""
    for node in nodes:
        for task in tasks:
            tracker = shadow_step(capsule, task, STRATEGIST, ShadowTracker())
            ledger.add(sign_shadow_record(
                node, capsule.capsule_id, task.seed, task.incident_class, task.params,
                tracker.wins == 1, tracker.invariant_hits, sim_time,
            ))


def _ddos_tasks(traffics: list[float], base_seed: int, site: str = "campus") -> list[Task]:
    return [_task("ddos_syn_flood", site, base_seed + i * 31, traffic_gbps=t)
            for i, t in enumerate(traffics)]


def _active(store: Store, ledger: ShadowLedger, capsule_id: str) -> bool:
    return derive_state(store, ledger, capsule_id, NODE_IDS).state == LifecycleState.ACTIVE


@dataclass
class Story:
    """The full dilemma-B narrative, run once; tests assert on its recorded checkpoints."""

    store: Store
    ledger: ShadowLedger
    events: EventStream
    p1: Capsule
    p2: Capsule
    h1: Capsule
    hiot: Capsule
    desc: Capsule
    suspects_before: list[str]
    adds_before: int
    promote_time: float
    first_report: ProbeReport
    probe_time: float
    passes: list[tuple[str, list[BisectStep]]]
    excisions: list[ExcisionResult]
    final_report: ProbeReport
    suspects_after: list[str]
    twin_tombstone_equal: bool
    twin_states_equal: bool
    duplicate_excision: ExcisionResult
    tombstone_after_duplicates: tuple[float, str]
    reuse_records: list[dict]
    reps: dict[str, float]
    promoted_authored_at_rep_time: dict[str, int]
    rogue_next_state: LifecycleState
    rogue_next_reason: str
    desc_quarantined_at: float
    desc_state_pre_rejury: object
    rejury_epoch: int
    rejury_outcome: JuryOutcome
    expected_committee: list[str]
    desc_state_post_rejury: object
    desc_state_after_fresh_records: object


@lru_cache(maxsize=1)
def story() -> Story:
    events = EventStream()
    store, ledger = Store(), ShadowLedger()

    # -- Admission through the genuine pipeline (real Pawl, real jury), one tick each --
    h1 = _measured("ddos_syn_flood", {"traffic_gbps": [1.0, 5.5], "site_class": ALL_SITES},
                   {"rate_limit_pps": 4000, "inspection_depth": 3},
                   [13000 + i * 11 for i in range(6)], "agent:site-a")
    p1 = _measured("ddos_syn_flood", P1_DIMS, P1_RULE, [11000 + i * 13 for i in range(6)], ROGUE)
    p2 = _measured("ddos_syn_flood", P2_DIMS, P2_RULE, [12000 + i * 17 for i in range(6)], ROGUE)
    hiot = _measured("iot_anomaly_burst", {"device_count": [300, 700], "site_class": ALL_SITES},
                     {"quarantine_scope": "flagged_only", "sampled_fraction": 1.0},
                     [14000 + i * 19 for i in range(6)], "agent:site-c")
    for capsule, tick in ((h1, 10.0), (p1, 12.0), (p2, 14.0), (hiot, 16.0)):
        state, reason = submit(capsule, store, AGENT_IDS, tick, strategist=STRATEGIST,
                               ledger=ledger, node_ids=NODE_IDS, emit=events.emit)
        assert state == LifecycleState.CANDIDATE, reason

    # -- Real mesh shadow → derived ACTIVE. p2's records come LATER so the organic descendant
    #    below derives from p1 (p2 is still CANDIDATE while the agent reuses). --
    _mesh_shadow(store, ledger, h1, _ddos_tasks([2.0, 3.5, 5.0], 8100), ("agent:site-b", "agent:site-c"), 17.0)
    _mesh_shadow(store, ledger, p1, _ddos_tasks([5.0, 6.0, 7.0], 8200), ("agent:site-b", "agent:site-c"), 17.5)
    _mesh_shadow(store, ledger, hiot,
                 [_task("iot_anomaly_burst", "campus", 8300 + i * 31, device_count=d)
                  for i, d in enumerate([400, 500, 600])],
                 ("agent:site-b", "agent:site-c"), 18.0)
    assert _active(store, ledger, h1.capsule_id)
    assert _active(store, ledger, p1.capsule_id)
    assert _active(store, ledger, hiot.capsule_id)

    # -- An organic derived descendant: site-a reuses ACTIVE p1 as prior; its refinement discovers
    #    a strictly better rule and authors derived_from=[p1] through its own real submit. --
    agent = FabricAgent(agent_id="site-a", site_class="branch", strategist=HeuristicStrategist(),
                        events=events, agent_ids=list(AGENT_IDS), node_ids=NODE_IDS,
                        store=store, ledger=ledger)
    for i in range(6):
        agent.handle_task(_task("ddos_syn_flood", "branch", 9000 + i, traffic_gbps=8.0), 20.0 + i)
    derived = [capsule for cid in store.live_ids()
               if (capsule := store.get(cid)) is not None and capsule.provenance.derived_from]
    assert len(derived) == 1 and derived[0].provenance.derived_from == [p1.capsule_id]
    desc = derived[0]
    _mesh_shadow(store, ledger, desc,
                 [_task("ddos_syn_flood", "branch", 9100 + i * 31, traffic_gbps=8.0) for i in range(3)],
                 ("agent:site-b", "agent:site-c"), 26.0)
    assert _active(store, ledger, desc.capsule_id)

    _mesh_shadow(store, ledger, p2, _ddos_tasks([7.0, 8.5, 10.0], 8400), ("agent:site-b", "agent:site-c"), 28.0)
    assert _active(store, ledger, p2.capsule_id)
    promote_time = 28.0

    suspects_before = suspects(store, ledger, NODE_IDS)
    adds_before = len(store.adds)

    # -- A twin node view (anti-entropy copy) for the duplicate-REVOKE chapter --
    store_b, ledger_b = Store(), ShadowLedger()
    reconcile((store, ledger), (store_b, ledger_b))

    # -- Sentinel probes its own local view; first tick after promotion is within one period --
    sentinel = Sentinel("agent:site-a", store, ledger, strategist=STRATEGIST, node_ids=NODE_IDS)
    probe_time = 30.0
    first_report = sentinel.tick(probe_time, emit=events.emit)
    assert first_report is not None and not first_report.clean

    # -- Loop: bisect → excise → re-probe, until the golden suite is clean (decision M5.3) --
    passes: list[tuple[str, list[BisectStep]]] = []
    excisions: list[ExcisionResult] = []
    report, sim = first_report, 31.0
    while not report.clean:
        assert len(passes) < 4, "excise→re-probe loop failed to converge"
        culprit, steps = bisect_culprit(store, ledger, STRATEGIST, sentinel.baselines,
                                        suspects(store, ledger, NODE_IDS),
                                        node_ids=NODE_IDS, sim_time=sim, emit=events.emit)
        assert culprit is not None
        passes.append((culprit, steps))
        excisions.append(excise(
            store, culprit, sim,
            reason=f"sentinel drift: {report.alarms[0].kpi} regression on the golden suite",
            probe_alarms=tuple(a.reason for a in report.alarms), emit=events.emit,
        ))
        sim += 1.0
        report = probe(store, ledger, STRATEGIST, sentinel.baselines, node_ids=NODE_IDS)
    final_report = report
    suspects_after = suspects(store, ledger, NODE_IDS)

    # -- Duplicate REVOKEs: the twin excises the same culprit independently and later; after
    #    anti-entropy both nodes converge on ONE dominant tombstone (the earliest). --
    first_culprit = passes[0][0]
    excise(store_b, first_culprit, sim + 1.0, reason="independent sentinel verdict on the twin")
    reconcile((store, ledger), (store_b, ledger_b))
    tomb_a, tomb_b = store.tombstones[first_culprit], store_b.tombstones[first_culprit]
    twin_tombstone_equal = tomb_a == tomb_b and tomb_a.sim_time == 31.0
    twin_states_equal = store == store_b and ledger == ledger_b
    duplicate_excision = excise(store, first_culprit, sim + 2.0, reason="duplicate revoke")
    tombstone_after_duplicates = (store.tombstones[first_culprit].sim_time,
                                  store.tombstones[first_culprit].reason)

    # -- Post-excision reuse: an unrelated honest capsule still serves live tasks --
    reuse_task = _task("ddos_syn_flood", "branch", 9500, traffic_gbps=4.5)
    agent.handle_task(reuse_task, 35.0)
    reuse_records = [r for r in events.of_type("REUSE") if r["task_id"] == reuse_task.task_id]

    # -- Reputation fold + the rogue's next (honest!) submission --
    reps = {aid: reputation(store, aid, ledger=ledger, node_ids=NODE_IDS) for aid in AGENT_IDS}
    promoted_authored_at_rep_time = {
        aid: sum(1 for cid in store.live_ids()
                 if (c := store.get(cid)) is not None and c.provenance.author == aid
                 and _active(store, ledger, cid))
        for aid in AGENT_IDS
    }
    rogue_next = _measured("ddos_syn_flood", {"traffic_gbps": [1.0, 5.0], "site_class": ALL_SITES},
                           {"rate_limit_pps": 2000, "inspection_depth": 3},
                           [15000 + i * 23 for i in range(6)], ROGUE)
    rogue_next_state, rogue_next_reason = submit(rogue_next, store, AGENT_IDS, 36.0,
                                                 strategist=STRATEGIST, ledger=ledger,
                                                 node_ids=NODE_IDS, emit=events.emit)

    # -- The quarantined honest descendant earns its way back: re-jury at the CURRENT epoch on its
    #    own evidence, then fresh shadow records re-promote it. --
    desc_lifecycle = store.lifecycle_of(desc.capsule_id)
    desc_quarantined_at = desc_lifecycle["quarantined_at"]
    desc_state_pre_rejury = derive_state(store, ledger, desc.capsule_id, NODE_IDS)
    rejury_epoch = 97  # the current epoch — not the frozen author_epoch the original committee used
    expected_committee = select_jury(AGENT_IDS, desc.capsule_id, rejury_epoch, desc.provenance.author)
    rejury_outcome = rejury(desc, store, AGENT_IDS, rejury_epoch, 40.0,
                            strategist=STRATEGIST, emit=events.emit)
    desc_state_post_rejury = derive_state(store, ledger, desc.capsule_id, NODE_IDS)
    _mesh_shadow(store, ledger, desc,
                 [_task("ddos_syn_flood", "branch", 9700 + i * 31, traffic_gbps=8.0) for i in range(3)],
                 ("agent:site-b", "agent:site-c"), 41.0)
    desc_state_after_fresh_records = derive_state(store, ledger, desc.capsule_id, NODE_IDS)

    return Story(
        store=store, ledger=ledger, events=events, p1=p1, p2=p2, h1=h1, hiot=hiot, desc=desc,
        suspects_before=suspects_before, adds_before=adds_before, promote_time=promote_time,
        first_report=first_report, probe_time=probe_time, passes=passes, excisions=excisions,
        final_report=final_report, suspects_after=suspects_after,
        twin_tombstone_equal=twin_tombstone_equal, twin_states_equal=twin_states_equal,
        duplicate_excision=duplicate_excision, tombstone_after_duplicates=tombstone_after_duplicates,
        reuse_records=reuse_records, reps=reps,
        promoted_authored_at_rep_time=promoted_authored_at_rep_time,
        rogue_next_state=rogue_next_state, rogue_next_reason=rogue_next_reason,
        desc_quarantined_at=desc_quarantined_at, desc_state_pre_rejury=desc_state_pre_rejury,
        rejury_epoch=rejury_epoch, rejury_outcome=rejury_outcome,
        expected_committee=expected_committee, desc_state_post_rejury=desc_state_post_rejury,
        desc_state_after_fresh_records=desc_state_after_fresh_records,
    )


# --- (a) the poison reaches derived-ACTIVE through the real pipeline ------------------

def test_poison_reaches_derived_active_through_the_genuine_pipeline():
    """Both poisons pass the real Pawl and a real jury quorum on honestly measured claims, earn
    real two-node shadow records, and stand derived-ACTIVE next to the honest capsules."""
    s = story()
    for poison in (s.p1, s.p2):
        cert = s.store.lifecycle_of(poison.capsule_id)["quorum_cert"]
        accepts = [v for v in cert["votes"] if v["verdict"] == "ACCEPT"]
        assert len(accepts) >= 2 and poison.provenance.author == ROGUE
        assert poison.capsule_id in s.suspects_before
    assert set(s.suspects_before) == {
        s.h1.capsule_id, s.p1.capsule_id, s.p2.capsule_id, s.hiot.capsule_id, s.desc.capsule_id
    }


# --- (b) a Sentinel raises DRIFT_ALARM within one probe period, naming the KPI --------

def test_sentinel_raises_drift_alarm_within_one_probe_period_naming_the_kpi():
    s = story()
    assert s.probe_time - s.promote_time <= PROBE_PERIOD
    alarms = [r for r in s.events.of_type("DRIFT_ALARM") if r["sim_time"] == s.probe_time]
    assert alarms, "the first probe after promotion must raise a drift alarm"
    assert any(a["kpi"] == "fp_quarantines" for a in alarms)
    for alarm in alarms:
        assert alarm["kpi"] in alarm["reason"] and "golden" in alarm["reason"]


# --- (c) bisect identifies exactly the culprit(s), one per excise→re-probe pass -------

def test_bisect_identifies_exactly_the_culprits_one_per_pass():
    """Two passes of standard halving over golden-suite replays find exactly the two poisons —
    never an honest capsule — with a BISECT event per step and O(log n) probes per pass."""
    s = story()
    culprits = [culprit for culprit, _steps in s.passes]
    assert set(culprits) == {s.p1.capsule_id, s.p2.capsule_id}
    assert len(culprits) == 2 and s.final_report.clean
    for _culprit, steps in s.passes:
        assert 1 <= len(steps) <= math.ceil(math.log2(len(s.suspects_before))) + 1
    bisect_events = s.events.of_type("BISECT")
    assert len(bisect_events) == sum(len(steps) for _c, steps in s.passes)
    assert all("bisect step" in e["reason"] for e in bisect_events)


# --- (d) Excision is surgical, never amnesic ------------------------------------------

def test_excision_removes_exactly_the_poisoned_subtree_and_memory_is_never_reset():
    """ACTIVE count drops by exactly the poisoned subtree {p1, p2, descendant} — never to zero;
    unrelated capsules still serve live tasks (a post-excision REUSE), and the store retains the
    full tombstoned history."""
    s = story()
    subtree = {s.p1.capsule_id, s.p2.capsule_id, s.desc.capsule_id}
    assert set(s.suspects_before) - set(s.suspects_after) == subtree
    assert len(s.suspects_after) == len(s.suspects_before) - len(subtree)
    assert s.suspects_after, "collective memory is never reset — ACTIVE count must not hit zero"
    assert set(s.suspects_after) == {s.h1.capsule_id, s.hiot.capsule_id}
    # The descendant is QUARANTINED (transitive derived_from closure), not tombstoned.
    assert s.excisions[0].quarantined == (s.desc.capsule_id,) or \
        any(e.quarantined == (s.desc.capsule_id,) for e in s.excisions)
    assert not s.store.is_tombstoned(s.desc.capsule_id)
    # Never-reset: every add — including both tombstoned poisons — is retained for audit.
    assert len(s.store.adds) >= s.adds_before
    for poison in (s.p1, s.p2):
        assert s.store.is_tombstoned(poison.capsule_id)
        assert poison.capsule_id in s.store.adds and s.store.get(poison.capsule_id) is None
    # Post-excision reuse: the unrelated honest capsule still wins arbitration on a live task.
    assert s.reuse_records and s.reuse_records[0]["capsule_id"] == s.h1.capsule_id


# --- (e) duplicate-REVOKE idempotence --------------------------------------------------

def test_duplicate_revokes_are_idempotent_by_tombstone_dominance():
    """Two nodes revoke the same culprit independently at different times: anti-entropy converges
    both stores to ONE dominant tombstone (the earliest), and a re-excision writes nothing new."""
    s = story()
    assert s.twin_tombstone_equal
    assert s.twin_states_equal
    assert s.duplicate_excision.quarantined == ()  # re-excision re-quarantines nothing
    sim_time, reason = s.tombstone_after_duplicates
    assert sim_time == 31.0 and "sentinel drift" in reason  # the original REVOKE record dominates


# --- (f) the reputation fold isolates the poison author --------------------------------

def test_reputation_fold_isolates_the_poison_author_at_the_pawl():
    """rep(rogue) = 1.0 − 2×0.4 = 0.2 < 0.3: the rogue's NEXT submission — an honest one — is
    auto-rejected by the existing Pawl check 5. Approving jurors on the poisons are slashed too."""
    s = story()
    assert s.reps[ROGUE] == 0.2 < REP_ISOLATION_FLOOR
    assert s.rogue_next_state == LifecycleState.REJECTED
    assert "below isolation floor" in s.rogue_next_reason
    # Jurors have skin in the game: each ACCEPT vote on a now-revoked capsule costs 0.2.
    accepts_on_revoked: dict[str, int] = {}
    for poison in (s.p1, s.p2):
        cert = s.store.lifecycle_of(poison.capsule_id)["quorum_cert"]
        for vote in cert["votes"]:
            if vote["verdict"] == "ACCEPT":
                accepts_on_revoked[vote["juror"]] = accepts_on_revoked.get(vote["juror"], 0) + 1
    for juror, n_accepts in accepts_on_revoked.items():
        assert juror != ROGUE  # sortition excluded the author from its own jury
        expected = round(1.0 + REP_PROMOTION_CREDIT * s.promoted_authored_at_rep_time[juror]
                         - REP_JUROR_SLASH * n_accepts, 4)
        assert s.reps[juror] == expected < 1.0


# --- (g) the quarantined honest descendant earns its way back ---------------------------

def test_quarantined_descendant_rejuried_at_current_epoch_repromotes_on_fresh_records():
    """Quarantine defeats stale glory: despite its old quorum of shadow records the descendant is
    not ACTIVE. A re-jury at the CURRENT epoch (fresh sortition committee) on its own evidence
    returns CANDIDATE, and only post-quarantine shadow records re-promote it."""
    s = story()
    assert s.desc_state_pre_rejury.state == LifecycleState.QUARANTINED
    assert s.desc_state_pre_rejury.records == 0  # pre-quarantine records no longer count
    assert s.rejury_outcome.accepted
    assert s.rejury_outcome.jurors == s.expected_committee
    assert s.rejury_epoch != s.desc.provenance.author_epoch
    assert s.desc_state_post_rejury.state == LifecycleState.CANDIDATE  # fresh cert, no fresh records yet
    assert s.desc_state_after_fresh_records.state == LifecycleState.ACTIVE
    assert s.desc_state_after_fresh_records.records == 6  # exactly the post-watermark records
    lifecycle = s.store.lifecycle_of(s.desc.capsule_id)
    assert lifecycle["quarantined_at"] == s.desc_quarantined_at  # the watermark travels with it
    assert lifecycle["quorum_cert"]["sim_time"] > s.desc_quarantined_at
