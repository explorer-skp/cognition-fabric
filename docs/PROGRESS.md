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
