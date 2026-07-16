# CLAUDE.md — Cognition Fabric (Code With Cisco Phase 2, Team Beacon)

Read `docs/BLUEPRINT.md` in full before writing any code. It is the source of truth for architecture,
schemas, algorithms, thresholds, and vocabulary. `docs/DEFENCE.md` explains why each choice exists;
`docs/DEMO_RUNBOOK.md` is the exact 10–15 minute experience this code must deliver. When a decision
is not covered by the blueprint, choose the simplest option that keeps the demo deterministic, and
leave a `# DECISION:` comment.

## Build order

Execute milestones M0 → M7 from BLUEPRINT §10, strictly in order. Do not start a milestone until the
previous one's acceptance criterion passes. After every milestone, `make demo-smoke` and `make test`
must be green. M0–M4 and M7 are MUST; if time runs short, a polished M4+M7 beats a broken M6.

## Environment & commands

- Python 3.11+, managed with `uv` (`uv venv`, `uv pip install -e ".[dev]"`). Runs fully offline.
- Dependencies: `pydantic`, `rich`, `pytest` only. Stdlib for everything else (hashlib, hmac,
  asyncio, json, random). No networking, no databases, no blockchain libraries.
- Provide a `Makefile`: `setup`, `test`, `demo-smoke` (≤20 s end-to-end run), `demo-ratchet`,
  `demo-chaos`, `clean-state` (wipes `.state/`).

## Determinism is sacred

- All randomness flows through explicitly passed, seeded `random.Random` instances — one stream per
  concern (taskgen, per-episode, per-juror held-out). Never `random.*` module-level, never
  `time.time()` in logic; use `world/simclock.py`.
- The demo scripts must produce byte-identical `events.jsonl` across runs on the same seed. There is
  a test asserting this (`tests/test_determinism.py`). This is non-negotiable: the live demo depends
  on it, and "our chaos is replayable" is a defence point.
- asyncio single process; the bus schedules deterministically (ordered delivery per sim tick).

## Code style

- Type hints everywhere; pydantic models must match BLUEPRINT §3 field names exactly — the schema is
  quoted in the defence, so field names are API.
- Everything a judge might inspect is a small pure function with unit tests: `pawl_check()`,
  `select_jury()`, `validate_capsule()`, `arbitrate()`, `refine_split()`, `bisect_culprit()`,
  `excise()`. No I/O inside these; they take data, return data + reason strings.
- All thresholds/constants in `fabric/config.py` with the BLUEPRINT names (JURY_K, QUORUM, HELDOUT_N,
  MIN_EFFECT, CLAIM_TOL, SHADOW_N, SHADOW_WIN, PROBE_PERIOD...). No magic numbers elsewhere.
- Every fabric event goes through `ui/events.py` as one structured JSONL stream; the TUI is a pure
  consumer. Event types: TASK, SOLVE, AUTHOR, PAWL_BLOCK, JURY_VERDICT, PROMOTED, REUSE, REVOKE,
  QUARANTINE, PROBE, DRIFT_ALARM, BISECT, REFINE, PARTITION, HEAL, CRASH, RESTART.
- Reason strings are user-facing: `PAWL_BLOCK` must say _which_ check failed and why, in one line
  (e.g., `ratchet monotonicity: capsule loosens COMPLIANCE bound inspection_depth 4→1`).

## Tests

- pytest per milestone acceptance criterion, plus `tests/test_dilemma_a.py`, `_b.py`, `_c.py` that
  encode the three judged dilemmas as executable claims (see BLUEPRINT §10 M3/M5/M6 for exactly what
  each must prove). These three files are demo material — keep them readable, with docstrings that
  state the dilemma in one sentence.
- Fast suite: whole `make test` under 60 seconds.

## Don'ts

- Don't call any LLM in the core path. `LLMStrategist` exists behind `--strategist=llm` as an
  interface implementation; a stub raising `NotImplementedError` with a clear message is acceptable.
- Don't rename blueprint vocabulary (Capsule, Pawl, Jury, Sentinel, Excision, Refine, ratchet
  staircase) in code, logs, or UI.
- Don't add features not traceable to BLUEPRINT §0. Depth over breadth is the judging criterion.
- Don't let `.state/` or `events.jsonl` into git; add `.gitignore` at M0 covering: `.state/`,
  `events.jsonl`, `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `recordings/`, `CLAUDE.md`,
  `.claude/`, `CLAUDE.local.md`.
- Commit conventions: plain conventional-commit messages authored solely by the repo's configured git
  user. Never add "Co-Authored-By" trailers, "Generated with" lines, tool bylines, or any AI
  attribution to commit messages, PR descriptions, branch names, or any git metadata. After the first
  commit of any session, run `git log -1 --format=full` and show the output as verification.
- Don't swallow errors in the fabric path — an unexpected exception in validation must reject the
  capsule with reason `internal_error`, never admit it (fail-secure, Phase 1 principle).

## Definition of done (before the event demo)

1. `make test` green, including the three dilemma tests and the determinism test.
2. `make demo-ratchet` and `make demo-chaos` each complete on fixed seeds with stable pacing and the
   headline numbers within BLUEPRINT §11 target ranges (tune `world/cost.py` / scenario constants,
   never the metrics code, to land them).
3. Full DEMO_RUNBOOK dry-run ≤ 12 minutes.
4. `README.md` (~1 page): what it is, quickstart, the three dilemma one-liners, and a pointer to the
   docs. Written last.

## Session protocol (this project is built across many fresh sessions)

One milestone per session. The repo is the only memory between sessions: green tests + git history +
`docs/PROGRESS.md`. Follow this in every session, unprompted:

**Start — before any edit:**

1. Read `docs/PROGRESS.md` (newest entry first), then only the BLUEPRINT sections the target
   milestone cites in §10.
2. Run `make test && make demo-smoke`. If anything is red, STOP and report — do not fix it by editing
   tests, and do not re-implement prior milestones.
3. Plan first: restate the milestone's acceptance criterion from BLUEPRINT §10 verbatim, list exactly
   which files you will create/modify, then wait for approval.

**During:**

- Touch only the planned files. Never modify an existing test (adding tests is fine). Never weaken
  the determinism rules. Anything the blueprint doesn't specify: simplest deterministic choice +
  `# DECISION:` comment — never invented behavior.

**End:**

- Run the full suite and show the pytest summary line (evidence, not claims).
- Append a dated entry to `docs/PROGRESS.md`: milestone, files touched, DECISION comments added,
  known issues, next step.
- Propose one git commit message. One milestone = one commit.
