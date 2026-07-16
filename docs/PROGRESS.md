# PROGRESS — session handoff log

Append one entry per session, newest at top. This file + green tests + git history are the ONLY
memory between sessions: if it isn't written here, the next session doesn't know it.

## Entry template

- **Session / date:**
- **Milestone(s) completed:**
- **Acceptance criterion result:** (paste the pytest summary line)
- **Files created/modified:**
- **DECISION comments added:** (file:line — one-line why)
- **Known issues / deferred:**
- **Next step:**

---

## S7 — 2026-07-16 (M6, out of order after M7)

- **Session / date:** S7 / 2026-07-16
- **Milestone(s) completed:** M6 (chaos injector + partition semantics, BLUEPRINT §6.2/§7.4-7.5).
  Built after M7 on explicit instruction — S6's "M6 deliberately skipped" gap is now filled, except
  that `demo/demo_chaos.py`'s narrated Act 3 still stops after Excision (mechanism is real and
  tested; not yet dramatized in that script's narration/pacing — see Known issues).
- **Acceptance criterion result:** `110 passed in 0.67s` (104 prior + 6 new,
  `tests/test_dilemma_c.py`). `(a)` two islands `{site-a,site-b}` | `{site-c,site-d,site-e}` each
  discover, jury-validate (real Pawl, real 3/3 quorum on honestly-measured claims), and mesh-promote
  their own ddos_syn_flood capsule through real `shadow_step` shadow while a chaos-injected
  partition blocks anti-entropy — both genuinely reach ACTIVE, each invisible on the other island.
  `(b)` heal (`reconcile_within_partition(nodes, None)`) converges every node's store+ledger; for an
  overlapping-context task every one of the 5 nodes independently calls the same pure `arbitrate()`
  and picks the identical winner. `(c)` three repeated arbitrations of the same pair cross
  `REFINE_THRESHOLD`; `refine_split` finds `traffic_gbps` as the separating dimension and produces
  two non-overlapping sub-ranges; both refined capsules are re-authored and reach ACTIVE through the
  genuine pipeline — both contexts survive. Plus units: `partitioned` gates cross-island only,
  `crash_node` round-trips a store intact (M2's guarantee, reusable), `provisional_cert_demotion`'s
  majority threshold. `make demo-smoke`, `demo-ratchet`, `demo-chaos` unaffected — all three still
  byte-identical across two runs after this session's fabric edits.
- **Files created/modified:**
  - New: `chaos/__init__.py`, `chaos/injector.py` (`Partition`, `partitioned`,
    `reconcile_within_partition`, `crash_node`), `tests/test_dilemma_c.py`.
  - Modified: `fabric/config.py` (`REFINE_THRESHOLD=3`), `fabric/jury.py` (`juror_verdict`/
    `validate_capsule` gain an optional `partition_view` param, default `None` = unchanged full-mesh
    behavior), `fabric/lifecycle.py` (`submit` threads `partition_view` through;
    `provisional_cert_demotion` + `demote_provisional`), `fabric/arbitration.py` (`refine_split`,
    `OverlapTracker`/`record_overlap`), `pyproject.toml` (+`chaos` package), `demo/demo_chaos.py`
    (Act 3's M6 note updated from "not implemented" to "implemented, not yet dramatized here"),
    `README.md` (Consistency dilemma + milestones-built section updated to match).
- **DECISION comments added:**
  - `fabric/lifecycle.py` — provisional-cert demotion lands on QUARANTINED, **not** a new
    ACTIVE→CANDIDATE transition edge. First attempt added that edge directly; caught immediately
    because `tests/test_m3_pipeline.py::test_lifecycle_transition_guard` already asserts
    ACTIVE→CANDIDATE is illegal, and CLAUDE.md forbids modifying an existing test. Reusing
    QUARANTINED is not a second meaning bolted onto the state — a minority-island cert and a
    poisoned ancestor are both "the evidence behind this promotion doesn't hold up," and M5's
    `quarantined_at` watermark in `derive_state` (fabric/gossip.py) already refuses pre-watermark
    records/certs, so the exact same re-promotion machinery applies with zero gossip.py changes.
  - `fabric/jury.py`/`fabric/lifecycle.py` — `partition_view` is `None`-default everywhere it
    threads through, so every M3–M5 caller is byte-identical; only a caller that explicitly passes a
    real view (M6-aware code) changes behavior.
  - `chaos/injector.py` — implements 3 of BLUEPRINT §9's 5 named faults (`partition`, `node_crash`;
    `heal` is `partition=None`). `poison_blatant`/`poison_subtle` are already proven end-to-end in
    `tests/test_dilemma_b.py` (M5) and `demo/demo_chaos.py` (M7); `flap` (repeatedly toggling
    partition) is exercised by no acceptance criterion this session and was left out.
  - `fabric/arbitration.py` — `refine_split` treats a capsule's declared `context.dims` as its
    "stored evidence range" (BLUEPRINT §7.4's exact phrase) — no separate evidence-range field
    exists or is needed. Picks the dim with least overlap fraction among dims shared by both
    capsules; ties/zero-separation fall back to "winner takes the overlap, loser superseded"
    (§7.4's stated fallback) by returning `loser_dims=None`.
  - `tests/test_dilemma_c.py` — seeds derived via `hashlib.sha256`, never Python's builtin `hash()`
    (PYTHONHASHSEED-salted, would silently break byte-identical output) — same rule already learned
    the hard way in S6's `demo_chaos.py`, applied proactively here from the first draft.
- **Known issues / deferred:**
  - `demo/demo_chaos.py`'s narrated Act 3 still stops after Excision — M6's mechanism is real and
    tested (`tests/test_dilemma_c.py`) but wiring a partition/heal/Refine beat into that script's
    live narration/pacing (RUNBOOK 8:45–10:15) is separate work, not done this session.
  - `docs/DEMO_RUNBOOK.md` itself was not edited (as before, `demo_chaos.py` narrates the gap
    inline). A future session wiring M6 into the demo should update both together.
  - `flap` (BLUEPRINT §9's fifth chaos fault, a partition that toggles repeatedly) has no dedicated
    function in `chaos/injector.py` — trivially composable from `reconcile_within_partition` +
    alternating `Partition`/`None`, but not built or tested.
- **Next step:** Wire M6 into `demo/demo_chaos.py`'s Act 3 (partition split, heal, Refine, minority-
  cert demotion beats) and update `docs/DEMO_RUNBOOK.md` to match, closing the one remaining gap
  between the codebase and the full scripted RUNBOOK. Otherwise M0–M7 are all complete.

---

## S6 — 2026-07-16 (M7 — M6 deliberately skipped)

- **Session / date:** S6 / 2026-07-16
- **Milestone(s) completed:** M7 (TUI + demo scripts). **M6 (chaos injector + partition semantics)
  was explicitly NOT built this session** — on direct instruction, this session jumped M5 → M7
  rather than follow BLUEPRINT's strict M0→M7 build order. This is a deliberate, acknowledged
  deviation, not an oversight: `tests/test_dilemma_c.py` does not exist, there is no
  `chaos/injector.py`, and RUNBOOK Act 3's partition/heal/Refine/minority-cert-demotion beats
  (8:45–10:15) are not implemented. `demo-chaos` says so explicitly at that beat instead of faking
  it. Dilemma C (BLUEPRINT §7) is therefore only two-thirds demonstrable: storage-eventually-
  consistent (CRDT merge, M4) and decisions-deterministic (`arbitrate()`, M4) are real; meaning-is-
  scoped (partition-driven Refine) is not.
- **Acceptance criterion result:** `104 passed in 0.62s` (86 prior + 18 new, `tests/test_m7_dashboard.py`).
  `make demo-smoke`, `make demo-ratchet`, `make demo-chaos` each byte-identical across two runs.
  `demo-ratchet --pace=live` completes in ~30s; `demo-chaos --pace=live` in ~75s — both individually
  well under their RUNBOOK act budgets (360s, 270s) and far under the ≤12 min M7 accept criterion;
  a single combined `ratchet && chaos` timed dry-run was not completed this session (interrupted;
  the two scripts' independent timings already bound the total).
- **Files created/modified:**
  - New: `ui/tui.py` (`DashboardState`, pure panel builders `mesh_table`/`fabric_table`/
    `ratchet_panel`/`economics_panel`/`event_log_panel`, `render_dashboard`, reducers
    `build_mesh_rows`/`build_fabric_rows`, the I/O `Dashboard` Live driver), `tests/test_m7_dashboard.py`,
    `README.md`.
  - Modified: `fabric/config.py` (cost weights uniformly scaled ×1.5), `demo/demo_ratchet.py` (full
    RUNBOOK Acts 0–2: cold open, twin-lane A/B, AUTHOR/JURY/PROMOTED/REUSE narration, a *live*
    crash+restart-with-memory beat), `demo/demo_chaos.py` (full RUNBOOK Act 3 up through Excision:
    pre-warmed 12-capsule fabric, blatant + subtle poison, Sentinel/bisect/Excision, honest M6
    deferral note).
- **DECISION comments added:**
  - `fabric/config.py` — every `COST_W_*` weight scaled by a single factor (1.5×). Proven
    `delta_pct`-neutral both analytically (`solve_cost(k·w) = k·solve_cost(w)` for fixed
    `(attempts, metrics)`, so every ratio-based threshold — MIN_EFFECT, CLAIM_TOL,
    AUTHOR_MIN_EFFECT, PROBE_TOL, every capsule's claimed delta — is unchanged) and empirically
    (full suite green before and after). Lands `demo-smoke`'s discovery medians at 28.0/31.6
    (BLUEPRINT §11 target 25–35). **Rejected**: `REUSE_REFINE_MAX` 2→1 as a lever to shrink the
    reuse/discovery ratio toward the 4–8 target — broke 8 tests (the derived-descendant mechanism
    in `test_m4_gossip_reuse.py` and all of `test_dilemma_b.py`) because every capsule's claim is
    measured through the *same* solve path (binding decision M3.1); reverted. The reuse/discovery
    ratio (~0.43) is therefore architecturally intrinsic to the current cost model — reuse_median
    (~13.6) stays above the 4–8 target, accepted rather than risking the dilemma tests' soundness.
  - `demo/demo_ratchet.py` — a demo-local storm shape (`n=80, funnel=15`, not the global
    `STORM_SIZE=60`) lands Lane A's savings at 40.5% (target 40–50%) and lead time at 6.5 sim-s
    (target 3–6) without touching any fabric constant; `demo_smoke.py`/`STORM_SIZE` untouched.
    Crash/restart-with-memory: the store round-trips through a real `PersistentStore` (M2's
    guarantee, re-proven live, asserted equal); the shadow ledger is reset to empty on "crash"
    (unpersisted per M4's own design) and re-syncs from peers via the mesh loop's *ordinary*
    anti-entropy — no special-cased recovery path.
  - `demo/demo_chaos.py` — honest capsules' context bands are deliberately kept outside the
    poison's golden-suite regression footprint (traffic 4/6/7/8); an overlapping honest capsule
    would win arbitration there and mask the poison from the Sentinel — the same masking
    `fabric/probes.py`'s in-isolation bisect exists to survive, now visible at the demo-authoring
    level too. Seeds are derived via `hashlib.sha256`, never Python's built-in `hash()` — the
    latter is per-process salted (`PYTHONHASHSEED`) and would have silently broken byte-identical
    output across runs; caught and fixed before it shipped.
  - `ui/tui.py` — panel builders are pure (data → Rich renderable, no I/O), unit-tested via
    `Console(record=True)`; only `Dashboard` (the `Live` wrapper) touches a terminal. Reputation is
    accepted as an externally-supplied field on `DashboardState` rather than derived purely from
    the event stream, since it is itself a pure fabric query (`fabric.excision.reputation`) the
    event log never carries as a field.
- **Known issues / deferred:**
  - M6 in full: chaos injector, partition/heal, Refine, minority-cert demotion, `tests/test_dilemma_c.py`.
  - `docs/DEMO_RUNBOOK.md` was not edited to reflect the M6 gap — `demo/demo_chaos.py` prints the
    deferral inline instead; a future session touching M6 should also update the RUNBOOK doc.
  - reuse_median (~13.6) remains above BLUEPRINT §11's 4–8 target band — architecturally tied to
    the shared solve path; would need a redesign of the claim-measurement path (out of scope for a
    "no mistakes" tuning pass) to close further.
  - A single end-to-end timed `ratchet && chaos --pace=live` dry-run was not completed (session
    interrupted); each script was independently timed well under its own RUNBOOK act budget.
- **Next step:** M6 — chaos injector + partition semantics (`tests/test_dilemma_c.py`): partition
  produces two capsules for one class, heal produces deterministic identical arbitration on every
  node, then a Refine split; both contexts survive. Then fold the M6 beats into `demo-chaos` and
  update `docs/DEMO_RUNBOOK.md`'s Act 3 accordingly.

---

## S5 — 2026-07-16 (M5)

- **Session / date:** S5 / 2026-07-16
- **Milestone(s) completed:** M5 (Sentinels + bisect + Excision — §6.4 complete). Golden-suite
  probes with one-sided harm KPIs, per-node Sentinel scheduler, in-isolation bisect halving,
  REVOKE-as-tombstone excision with transitive quarantine, the derived reputation fold wired into
  Pawl check 5, and current-epoch re-jury for quarantined descendants.
- **Acceptance criterion result:** `86 passed in 0.60s` (73 prior + 13 new). `tests/test_dilemma_b.py`
  proves all seven acceptance claims on ONE recorded narrative (module-cached `story()`): (a) **two**
  subtle poisons by `agent:site-e` (binding decision amendment: two, so isolation is organic) pass the
  GENUINE pipeline — real Pawl, 3/3 jury on honestly *measured* −44%/−46% `solve_cost` claims (reuse
  attempts-savings dominate; no thresholds touched, `world/scenarios.py` **untouched** — M5.6's fp
  knob proved unnecessary), real two-node `shadow_step` records → derived-ACTIVE; (b) the first
  Sentinel tick ≤ one `PROBE_PERIOD` after promotion raises `DRIFT_ALARM` naming `fp_quarantines`
  (poison anchors the 3-attempt reuse budget in a bad basin: fp 0→1..2 on in-context goldens);
  (c) two excise→re-probe passes, each bisect ≤ ⌈log₂ 5⌉+1 probes with a `BISECT` event per step,
  find exactly {poison1, poison2} — poison2 *masks* poison1 via arbitration until excised; (d) ACTIVE
  drops 5→2, exactly the poisoned subtree {p1, p2, organic descendant(QUARANTINED)}, never zero; a
  post-excision `REUSE` fires on the honest capsule; every add incl. both tombstones retained
  (never-reset); (e) duplicate REVOKEs from a twin node converge by tombstone dominance to the
  earliest record, stores/ledgers digest-equal; (f) fold: rogue = 1.0 − 2×0.4 = 0.2 < 0.3 → next
  (honest!) submission dies at Pawl "below isolation floor"; approving jurors slashed −0.2/cert;
  (g) the quarantined descendant re-juried at a fresh epoch (committee == `select_jury` at that
  epoch) returns CANDIDATE and re-promotes on exactly 6 post-watermark records.
  `tests/test_m5_immune.py` units: probe determinism, tombstoned-ancestor derivation block,
  quarantine watermark (fresh cert + fresh records), reputation fold incl. floor-at-0 and
  ACCEPT-only juror slash, transitive-closure excise skipping settled states.
  `make demo-smoke` byte-identical across runs **and vs the M4 tree** (no live-path changes).
- **Files created/modified:**
  - New: `fabric/probes.py` (`GOLDEN_SUITE` 12 pinned scenarios, `clean_baselines`, `probe`/
    `ProbeReport`, `Sentinel`, `suspects`, `bisect_culprit`), `fabric/excision.py` (`descendants`,
    `excise`/`ExcisionResult`, `reputation` fold, `rejury`), `tests/test_dilemma_b.py`,
    `tests/test_m5_immune.py`.
  - Modified: `fabric/config.py` (`PROBE_TOL = DRIFT_THRESHOLD`, `REP_PROMOTION_CREDIT`),
    `fabric/gossip.py` (`derive_state` gains lineage + quarantine-watermark clauses;
    `_tombstoned_ancestry`), `fabric/lifecycle.py` (`submit` derives the author's reputation via the
    fold when no `pawl_ctx` is supplied; optional `ledger`/`node_ids` params).
- **DECISION comments added:**
  - `fabric/config.py` — `PROBE_TOL` defined *from* `DRIFT_THRESHOLD` so the M5 name and the §6.4
    name can never diverge.
  - `fabric/gossip.py` — decision M5.5's clauses **compose**: an absolute no-tombstoned-ancestor
    rule would contradict §4's QUARANTINED→re-jury→re-promote path; (a) guards the replication
    window before the quarantine meta lands, (b) governs after (fresh cert + fresh records only).
  - `fabric/probes.py` — golden suite is pinned *data*, lives beside its replayer (thresholds stay
    in config); Sentinel is harness-first like M3's shadow staging (`agents/` outside M5 scope —
    live tick wiring is M6/M7 demo work); bisect probes halves **in isolation** (disable the
    window-complement, not the half) because arbitration lets one ACTIVE capsule mask another —
    in-isolation probing keeps "the window always contains a culprit" true under masking.
  - `fabric/lifecycle.py` — M5.4 wiring: default `pawl_ctx` derives reputation as the pure fold
    (lazy import; excision consumes lifecycle's transition guard).
  - `fabric/excision.py` — quarantine lands only on CANDIDATE/ACTIVE; settled states are skipped,
    not resurrected.
- **Known issues / deferred:**
  - Sentinel `tick()` is not yet called from the live agent loop (scope lock: no `agents/`); M6's
    chaos loop / M7's demo scripts wire the cadence. Same for emitting BISECT/REVOKE from a demo.
  - Reputation decay/recovery (Pawl reason says "until decay recovery") still has no decay constant
    — isolation is currently permanent absent new promotions; revisit if a demo beat needs it.
  - `rejury` re-assembles the ~15-line quorum-cert dict (shape identical to `validate_capsule`'s);
    `fabric/jury.py` was out of scope — if M6 touches jury.py, extract a shared `_build_cert`.
  - Poison arbitration masking is real and documented: a poison masked by a *honest* winner never
    manifests through the live path, so the Sentinel (correctly) cannot see it as drift.
- **Next step:** M6 — chaos injector + partition semantics (`tests/test_dilemma_c.py`): partition
  produces two capsules for one class, heal → deterministic identical arbitration everywhere, then a
  Refine split; both contexts survive.

---

## S4 — 2026-07-16 (M4)

- **Session / date:** S4 / 2026-07-16
- **Milestone(s) completed:** M4 (Gossip + reuse + ratchet metrics + twin-lane A/B). Mesh-wide shadow
  staging (binding decision M4.2, **amended in-session** to records-based derived promotion),
  fabric-query-before-solve reuse, organic derived capsules, and the pure metrics reducer.
  **PS requirements 1–5 are now all demonstrable** (changing conditions → TaskGen drift; validated
  reuse → Pawl/Jury/derived-shadow; drift/poison border → Pawl carried forward; consistency →
  deterministic `arbitrate()` + CRDT gossip convergence; and the ratchet — the measured Lane A vs
  Lane B economics).
- **Acceptance criterion result:** `73 passed in 0.54s` (52 prior + 21 new). New:
  `tests/test_m4_gossip_reuse.py` (applies/arbitrate incl. the **hash tie-break** and priority
  dominance; `verify_push` accepts a valid cert and rejects a tampered juror sig / unknown author;
  `derive_state` promotes at mesh quorum and is **unreachable from a single node's records alone**,
  needs a win-supermajority + zero invariant hits, ignores foreign-node records; **gossip
  convergence** property — two divergent `(store, ledger)` states reconcile to identical digests,
  order-independently; a **derived capsule carries `derived_from`**), and `tests/test_m4_ratchet.py`
  (repeat incidents reuse at **≥3 non-author sites** at **reuse ≤ 0.5× discovery**; staircase
  **monotone non-increasing and steps down**; **Lane A < Lane B** on both the shaped and the natural
  stream; **Lane B ≡ the fabric-off baseline** byte-for-byte; determinism; insight lead times).
  `make demo-smoke` (M4 twin-lane block, byte-identical across runs):
  ```
  # demo-smoke (M4): twin-lane repeat-incident storm, seed=424242, tasks=60 (Lane A fabric ON · Lane B fabric OFF)
  cert_expiry_storm    discovery_median=  18.67  reuse_median=    -    ratio=   -   staircase=18.7→18.6
  ddos_syn_flood       discovery_median=  21.06  reuse_median=   9.06  ratio= 0.43  staircase=21.1→8.9
  # ratchet: authored=5  promoted(mesh)=15  non-author reuse sites=4  median insight lead=12.0 sim-s
  # economics: Lane A cumulative=859.6  Lane B cumulative=1243.6  saved=30.9%  (…absolute band tuned in M7)
  ```
- **Files created/modified:**
  - New: `fabric/gossip.py` (ShadowRecord/ShadowLedger, sign/verify, build/verify/apply_push,
    `derive_state`, `digest`, `reconcile`), `fabric/arbitration.py` (`applies`, `Applicable`,
    `active_matches`, `arbitrate`), `ui/metrics.py` (pure reducer), `tests/test_m4_gossip_reuse.py`,
    `tests/test_m4_ratchet.py`.
  - Modified: `fabric/config.py` (`AUTHOR_MIN_EPISODES`, `AUTHOR_MIN_EFFECT`, `GOSSIP_PERIOD`,
    `SHADOW_QUORUM_N/WIN`, `SHADOW_MIN_NODES`), `agents/agent.py` (`FabricAgent`, `run_fabric_storm`,
    `run_twin_lane`; `run_baseline_storm` gained an optional injected `tasks` — default unchanged, so
    Lane B stays byte-identical to M1), `demo/demo_smoke.py` (twin-lane metrics block in `main()`;
    `run_smoke`/`_format` untouched for the determinism test).
- **DECISION comments added:**
  - `fabric/config.py` — mesh-shadow constants named `SHADOW_QUORUM_N=6 / SHADOW_QUORUM_WIN=5 /
    SHADOW_MIN_NODES=2`, **distinct** from the legacy single-node `SHADOW_N=10 / SHADOW_WIN=7`
    (still pinned by `tests/test_m3_pipeline.py`; the mesh model supersedes it on the live path).
  - `fabric/gossip.py` — the `SHADOW_RECORD` OR-set lives here, not in `store.py` (M4 scope lock
    excludes store.py), reconciled by the same anti-entropy pass; ACTIVE is derived, never stored or
    gossiped; transport is the in-process orchestrator (§13, simulated network / real algorithms).
  - `fabric/arbitration.py` — priority class compared lexicographically (§7); hash tie-break = the
    smaller `sha256(capsule_id)` wins.
  - `agents/agent.py` — Lane A is a sequential in-process orchestrator (gossip by direct verified
    calls, transport simulated); shaped-supply is a *test/demo* concern only; declared context =
    per-dim [min,max] over the recent evidence window (never wildcard); the derived-authoring
    trigger compares episode **impact** (search effort excluded — a derived capsule captures a better
    *rule*, not a cheaper search); one base-authoring attempt per class per node (no churn).
  - Decision M4.4 (lane seed isolation) is a **no-op**: `world/taskgen.generate` already derives each
    task's fields from `(run_seed, task_index)` only, independent of `n`/lane/fabric — verified, so
    `world/taskgen.py` was not touched.
- **Known issues / deferred:**
  - Economics band (insight lead ≈ 12 sim-s vs §11's 3–6; Lane A/B gap) is not yet tuned — deferred
    to M7 per plan/amendment; the *mechanism* is what M4 proves.
  - Live periodic anti-entropy is a full all-pairs reconcile each `GOSSIP_PERIOD`; in M4 (no drops)
    promotion push already propagates, so reconcile is the backstop whose correctness the convergence
    property test owns. Partitions/heal + provisional-cert demotion are M6.
  - `derived_from` wiring in the storm is best-effort (rarely fires when priors are already
    near-optimal); the requirement is guaranteed by the focused unit test.
- **Next step:** M5 — Sentinels + bisect + Excision (`tests/test_dilemma_b.py`): subtle poison passes
  admission, a Sentinel flags it, bisect finds it, Excision removes it + its (now-organic) descendant
  while unrelated capsules and their reuse behavior are untouched.

---

## S3 — 2026-07-16 (M3)

- **Session / date:** S3 / 2026-07-16
- **Milestone(s) completed:** M3 (Pawl + Jury + lifecycle: full §5 pipeline, §6.1 ordered checks,
  §4 transition machine, shadow staging harness).
- **Acceptance criterion result:** `52 passed in 0.11s` (32 prior + 20 new). `tests/test_dilemma_a.py`
  proves all five acceptance claims: (a) fabricated −90% claim dies at `counterfactual replay`
  (reproduces at ≈ −55%); (b) overfit capsule — test deterministically scans 80 seeds and
  cherry-picks the 6 luckiest for a mediocre `sampled_fraction=0.1` iot rule (lucky median ≈ −69%,
  population median ≈ +13%) — passes counterfactual, dies at `author-blind held-out`; (c)
  true-but-unsafe subnet-quarantine capsule (genuine ≈ −55% measured gain) dies at
  `invariant/conformance` naming `no_blanket_subnet_block_without_compliance_class`; (d) honest
  capsule passes Pawl, 3/3 jury quorum, 10/10 shadow wins → ACTIVE with confidence 1.0 and a
  quorum cert whose signatures verify; (e) every rejection asserts its stage's reason string.
  `make demo-smoke` output byte-identical to M2 (no live-path changes).
- **Files created/modified:**
  - New: `fabric/pawl.py` (ordered §6.1 checks, `PawlContext`/`PawlResult`), `fabric/jury.py`
    (`select_jury`, `sample_episode`, `replay`, stages 3–5, `vote_payload`, `validate_capsule`),
    `fabric/lifecycle.py` (§4 transition guard, `submit`, `shadow_step`/`shadow_verdict`/
    `run_shadow`, injected no-op emitter), `tests/test_dilemma_a.py`, `tests/test_m3_pipeline.py`.
  - Modified: `fabric/config.py` (`REUSE_REFINE_MAX`, `HELDOUT_WIN`, `MIN_N_EPISODES`,
    `RATE_WINDOW_S`, `RATE_PER_REPUTATION`, `CONTEXT_MAX_WIDTH_FRAC`, `CLASS_PARAM_SPACE`),
    `fabric/registry.py` (`ACTION_DIMENSIONS`, `SCENARIO_DIMENSIONS`, `Protected` +
    `PROTECTED_BOUNDS`, `context_priority_class`), `agents/strategist.py` (binding decision M3.1
    only: prior merged over `DEFAULT_ACTION`, budget `1 + REUSE_REFINE_MAX`; cold path untouched).
- **DECISION comments added:**
  - `fabric/config.py` — `CONTEXT_MAX_WIDTH_FRAC=0.8` (full-width interval reads as wildcard);
    `CLASS_PARAM_SPACE` mirrors taskgen's drift-clamped ranges, lives in config (scope lock
    excludes `world/`).
  - `fabric/registry.py` — only `inspection_depth` carries a static COMPLIANCE floor (=2, the
    DEFAULT_ACTION baseline); `block_ttl_s` reversibility stays a dynamic invariant so unsafe
    capsules reach stage 5; a context omitting `site_class` is COMPLIANCE-scoped (fail-secure).
  - `fabric/jury.py` — '‖' in sortition = ':'-joined concatenation; non-positive baseline metric
    scores an episode 0% (no division blow-up, no free pass); stage 5 checks the *declared* rule
    (merged over `DEFAULT_ACTION`) against every episode context — refinement patching an unsafe
    rule live does not save the capsule.
  - `fabric/lifecycle.py` — store meta is LWW with a JSON tie-break (M2), so callers write at most
    one lifecycle snapshot per sim tick (`submit` validates each logical transition but persists
    only the outcome); shadow win/loss judged on `solve_cost` regardless of claim metric, tie =
    loss; QUARANTINED reachable from CANDIDATE and ACTIVE.
  - `agents/strategist.py` — partial prior rules merge over `DEFAULT_ACTION` for a complete,
    deterministic start.
- **Known issues / deferred:**
  - `partition_view` is the sorted full agent set (binding decision M3.4); M6 fills it with real
    connectivity views. Rate/reputation inputs (`PawlContext`) are caller-supplied; live tracking
    arrives with the agent-loop wiring (M4) and slashing (M5).
  - Shadow staging is harness-only (`run_shadow` over provided tasks); live agent-loop wiring,
    capsule authoring, and REUSE events are M4. `agents/agent.py` untouched.
  - Dev keyring keys are derivable — held-out blindness rests on the keyring interface, not the
    dev keys (documented stub seam, §13).
- **Next step:** M4 — gossip + fabric-query-before-solve reuse + ratchet metrics + twin-lane A/B.

---

## S2 — 2026-07-16 (M2)

- **Session / date:** S2 / 2026-07-16
- **Milestone(s) completed:** M2 (Capsule schema + signing + OR-set store + JSONL persistence +
  restart-reload).
- **Acceptance criterion result:** `32 passed in 0.15s` (20 prior + 12 new in
  `tests/test_m2_capsule_store.py`). Acceptance test `test_crash_reload_roundtrip`: a `PersistentStore`
  with 3 adds + 1 tombstone + 2 meta updates is dropped ("crash") and reloaded from
  `.state/<agent>/store.jsonl` with full store equality, tombstone dominance, and latest-lifecycle
  state intact. `test_crash_at_append_boundary_reloads_cleanly` proves a truncated final line reloads
  cleanly. `make demo-persist` is the manual form (crash→reload story prints identically). `make
  demo-smoke` output unchanged (M2 touches no demo/world path).
- **Files created/modified:**
  - New: `fabric/keyring.py` (HMAC dev keyring, §13 stub), `fabric/capsule.py` (pydantic §3 schema +
    `LifecycleState` enum + `canonical_body`/`compute_id`/`build_capsule`/`check_integrity`),
    `fabric/store.py` (`Store` pure OR-set + `PersistentStore` JSONL wrapper),
    `tests/test_m2_capsule_store.py`, `demo/demo_persist.py`.
  - Modified: `Makefile` (+`demo-persist` target and `.PHONY`).
- **DECISION comments added:**
  - `fabric/keyring.py` — dev keys derived deterministically from identity via domain-separated
    SHA-256; drop-in for real PKI, interface unchanged (§13).
  - `fabric/capsule.py` — `check_integrity` named distinctly from M3's `validate_capsule()`
    (Pawl/Jury), which M2 does not build.
  - `fabric/store.py` — meta update is a full-snapshot LWW replace (no per-field merge); tombstone
    merge keeps the deterministic-min `(sim_time, reason)` so merge stays commutative/associative;
    `.state` root is a path literal (default arg), not a config threshold; on load, a corrupt line is
    tolerated ONLY as the final line (crash mid-append) — earlier corruption raises (fail-secure).
- **Known issues / deferred:**
  - `capsule_id`/`sig` cover the immutable body only; `lifecycle` is mutable node-local metadata,
    excluded from both (binding decision M2.1) and carried via `metas` LWW.
  - `Store.merge` is the CRDT primitive gossip (M4) will drive; no gossip/anti-entropy wired yet.
  - Lifecycle is an enum only — no transition machine, Pawl, or Jury (M3).
- **Next step:** M3 — Pawl + Jury + lifecycle transitions + shadow staging; `tests/test_dilemma_a.py`.

---

## S1 — 2026-07-16 (M0 + M1)

- **Session / date:** S1 / 2026-07-16
- **Milestone(s) completed:** M0 (World) and M1 (Agents baseline, fabric OFF).
- **Acceptance criterion result:** `20 passed in 0.04s` — includes `tests/test_determinism.py`,
  `tests/test_m0_world.py`, `tests/test_m1_baseline.py`. `make demo-smoke` produces byte-identical
  stdout **and** `events.jsonl` across two runs (M0 accept: 20-task metrics identical across runs;
  M1 accept: 5 agents process a 60-task storm, per-class median costs ~18–23, halves within a flat
  band). Bootstrap: private repo `explorer-skp/cognition-fabric`, `main` pushed.
- **Files created/modified:**
  - Bootstrap: `.gitignore` (+ `*.egg-info/`,`build/`,`dist/`), `pyproject.toml`, `Makefile`,
    package `__init__.py`s, `uv.lock`.
  - M0: `fabric/config.py`, `fabric/registry.py`, `world/{simclock,bus,scenarios,cost,taskgen}.py`,
    `demo/{demo_smoke,demo_ratchet,demo_chaos}.py`, `tests/{test_determinism,test_m0_world}.py`.
  - M1: `ui/events.py`, `agents/{strategist,agent}.py`, extended `demo/demo_smoke.py`, modified
    `fabric/config.py` (AGENTS, MAX_ATTEMPTS, STORM_SIZE, DEFAULT_ACTION), `tests/test_m1_baseline.py`.
- **DECISION comments added:**
  - `fabric/config.py` — M0 implements the first 3 of §8's six incident classes; scenario-internal
    shape coefficients live in `world/scenarios.py` (locality), not config.
  - `fabric/registry.py` — `dc` is the compliance-classed site (allowed subnet-wide blocks).
  - `fabric/config.py` — `DEFAULT_ACTION` sits off every class optimum on purpose so cold discovery costs.
- **Known issues / deferred:**
  - Headline first-solve band (§11: 25–35) not yet tuned; per-class medians land ~18–23. Tuning is a
    definition-of-done item for the ratchet milestone, not an M1 gate.
  - Bus partition/drop hooks present but inert (chaos milestone M6).
  - Reuse cost (prior-seeded search) not implemented — cold hill-climb still probes neighbors even
    from an optimal start; M4 makes reuse cheap (0–2 refinement attempts).
- **Next step:** M2 — Capsule schema + signing + OR-set store + JSONL persistence + restart-reload.

---

## S0 — 2026-07-16 (bootstrap, no code)

- Repo initialized with `docs/{BLUEPRINT,DEFENCE,DEMO_RUNBOOK,PROGRESS}.md`.
- Phase 1 artifacts available for porting: registry structure, invariants, priority lattice,
  `arbitrate()` (see BLUEPRINT §1).
- **Next step:** M0 (world: simclock, bus, registry, 3 scenario classes, cost model, taskgen).
