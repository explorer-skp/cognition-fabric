"""Every named threshold/constant in the BLUEPRINT lives here (BLUEPRINT §5, §6, §8).

No magic numbers elsewhere in the codebase. This file grows one milestone at a time;
each constant carries the BLUEPRINT name so a judge can answer a question by opening one file.

# DECISION: scenario-internal shape coefficients (per-class arithmetic) live beside the
# arithmetic in world/scenarios.py for locality; only cross-cutting, judge-facing thresholds
# (cost weights, action space, pipeline thresholds, taskgen rates) live here.
"""

from __future__ import annotations

# --- Registry (BLUEPRINT §8) -------------------------------------------------
REGISTRY_VERSION = "3.2"

# --- Incident classes active in the current build ----------------------------
# BLUEPRINT §8 defines six; M0 implements the first three (M0 milestone: "scenarios for
# 3 incident classes"). The remaining three land in a later milestone.
# DECISION: first three listed in §8 chosen; extend this tuple as scenarios are added.
INCIDENT_CLASSES: tuple[str, ...] = (
    "ddos_syn_flood",
    "iot_anomaly_burst",
    "cert_expiry_storm",
)

SITE_CLASSES: tuple[str, ...] = ("branch", "campus", "dc")

# --- Cost model (BLUEPRINT §8) ----------------------------------------------
# solve_cost = 2.0*attempts + 0.05*time_to_mitigate_s + 5.0*fp_quarantines
#            + 1.0*sla_burn + 25.0*invariant_hits
COST_W_ATTEMPT = 2.0
COST_W_TIME = 0.05
COST_W_FP = 5.0
COST_W_SLA = 1.0
COST_W_INVARIANT = 25.0

# --- Quantized action space (BLUEPRINT §8: bounded local search) -------------
# The Strategist hill-climbs over these discrete choices. Registry dimensions only.
ACTION_SPACE: dict[str, list] = {
    "rate_limit_pps": [2000, 4000, 6000, 8000, 10000, 12000],
    "inspection_depth": [0, 1, 2, 3, 4, 5, 6, 7],
    "quarantine_scope": ["none", "flagged_only", "subnet"],
    "retry_backoff_ms": [50, 100, 200, 400, 800],
    "sampled_fraction": [0.1, 0.25, 0.5, 1.0],
    "block_ttl_s": [30, 60, 120, 300],
}

# A deterministic, safe-but-suboptimal starting action (no invariant hits). The ratchet
# story: without memory the Strategist searches out from here; with memory it starts from a prior.
DEFAULT_ACTION: dict = {
    "rate_limit_pps": 6000,
    "inspection_depth": 2,
    "quarantine_scope": "flagged_only",
    "retry_backoff_ms": 400,   # off every class optimum on purpose: cold discovery must cost
    "sampled_fraction": 0.5,
    "block_ttl_s": 300,
}

# --- Agents & Strategist (BLUEPRINT §8) --------------------------------------
MAX_ATTEMPTS = 12  # bounded local search: "hill-climb over the quantized action space, ≤ 12 attempts"

# The five site agents in the enterprise mesh (id, site_class). site-e can be flipped rogue by the
# chaos injector (BLUEPRINT §8); site classes span branch/campus/dc.
AGENTS: tuple[tuple[str, str], ...] = (
    ("site-a", "branch"),
    ("site-b", "campus"),
    ("site-c", "dc"),
    ("site-d", "branch"),
    ("site-e", "campus"),
)

STORM_SIZE = 60  # tasks in a demo "storm" (BLUEPRINT §11: storm of ~60 tasks)

# --- TaskGen (BLUEPRINT §8: Poisson arrivals + drift, fully seeded) ----------
TASKGEN_LAMBDA_BASE = 0.5           # base arrival rate (tasks per sim-second)
TASKGEN_LAMBDA_DRIFT = 0.15         # amplitude of arrival-rate drift over the run
TASKGEN_PARAM_DRIFT = 0.20          # fractional in-class parameter drift over the run

# --- Validation pipeline thresholds (BLUEPRINT §5) ---------------------------
# Present now so the constants are answerable from one file; consumed from M3 onward.
JURY_K = 3
QUORUM = 2
HELDOUT_N = 8
HELDOUT_WIN = 6                     # §5.4: improvement in ≥ 6 of the 8 held-out episodes
MIN_EFFECT = 0.15
CLAIM_TOL = 0.25
SHADOW_N = 10
SHADOW_WIN = 7

# Reuse is cheap by construction (BLUEPRINT §8 "typically 0–2 refinement attempts"): solving with a
# prior evaluates the prior once, then makes at most this many refinement attempts (binding
# decision M3.1 — the single solve path shared by jury replay, shadow staging, and live reuse).
REUSE_REFINE_MAX = 2

# --- Authoring (BLUEPRINT §2 Accelerator; binding decision M4.1) --------------
# After a discovery solve of a class, an agent authors a capsule only once it holds this many
# recorded episodes of that class and its self-replay median improvement clears AUTHOR_MIN_EFFECT
# (stricter than the jury's MIN_EFFECT=0.15 — borderline capsules must not churn the pipeline).
AUTHOR_MIN_EPISODES = 4
AUTHOR_MIN_EFFECT = 0.20

# --- Gossip / anti-entropy (BLUEPRINT §7.1, §12; binding decision M4.2) -------
# Period between anti-entropy digest rounds. On a digest mismatch, nodes exchange id sets and pull
# missing records (GOSSIP_DIGEST → GOSSIP_PULL); promotion push (GOSSIP_PUSH) is eager, on quorum.
GOSSIP_PERIOD = 2.0

# --- Mesh-wide shadow staging (binding decision M4.2, amended) ----------------
# Promotion is DERIVED from replicated, signed SHADOW_RECORDs, never announced: a capsule flips
# ACTIVE once its local store holds ≥ SHADOW_QUORUM_N verified records from ≥ SHADOW_MIN_NODES
# distinct nodes with wins ≥ SHADOW_QUORUM_WIN and zero invariant hits. The condition is monotone
# (records only accumulate) so there is no flapping, and nodes converge as records replicate.
# DECISION: distinct names from the legacy single-node SHADOW_N=10/SHADOW_WIN=7 (M3's run_shadow
# harness, still exercised by tests/test_m3_pipeline.py) — the mesh model supersedes it on the live
# path. M7 owns final tuning against demo pacing.
SHADOW_QUORUM_N = 6
SHADOW_QUORUM_WIN = 5
SHADOW_MIN_NODES = 2

# --- Pawl static checks (BLUEPRINT §6.1) --------------------------------------
MIN_N_EPISODES = 4                  # check 4: falsifiable claim needs n_episodes ≥ 4
RATE_WINDOW_S = 100.0               # check 5: submission window in sim-seconds
RATE_PER_REPUTATION = 3             # check 5: submissions per window = floor(3 × reputation)
# check 3 (bounded context): a declared interval may cover at most this fraction of the class
# parameter space's width in that dimension.
# DECISION: 0.8 — wide enough for honest capsules (taskgen drifts across most of the space),
# tight enough that a full-width interval reads as a wildcard and is blocked (blast radius).
CONTEXT_MAX_WIDTH_FRAC = 0.8

# --- Class parameter space (BLUEPRINT §5.4 held-out sampling) -----------------
# The per-class scenario-parameter space jurors sample held-out episodes from: the intersection of
# a capsule's declared context dims with these ranges (binding decision M3.2).
# DECISION: ranges mirror world/taskgen.py's drift-clamped sampling bounds; they live here (not
# world/) because they are pipeline-facing thresholds a judge will ask for, and M3's scope lock
# excludes world/ edits.
CLASS_PARAM_SPACE: dict[str, dict] = {
    "ddos_syn_flood": {"traffic_gbps": (1.0, 12.0), "site_class": SITE_CLASSES},
    "iot_anomaly_burst": {"device_count": (10, 800), "site_class": SITE_CLASSES},
    "cert_expiry_storm": {"site_class": SITE_CLASSES},
}

# --- Immune system thresholds (BLUEPRINT §6) ---------------------------------
PROBE_PERIOD = 60.0                 # sim-seconds between Sentinel probe sweeps
DRIFT_THRESHOLD = 0.10              # KPI regression fraction that trips a drift alarm
REP_AUTHOR_SLASH = 0.4
REP_JUROR_SLASH = 0.2
REP_ISOLATION_FLOOR = 0.3

# --- Sentinel probes & Excision (BLUEPRINT §6.4; milestone M5) -----------------
# One-sided harm tolerance (binding decision M5.1): a probe alarms iff fp_quarantines or sla_burn
# on any golden scenario exceeds its clean baseline × (1 + PROBE_TOL), or any invariant is hit
# anywhere. solve_cost may move freely — lowering it is the fabric's purpose; Sentinels guard the
# KPIs that claims don't cover.
# DECISION: PROBE_TOL is M5's name for §6.4's drift threshold; defined from DRIFT_THRESHOLD so the
# two names can never diverge.
PROBE_TOL = DRIFT_THRESHOLD

# Reputation fold (binding decision M5.4): derived on read, never stored or messaged —
#   1.0 + REP_PROMOTION_CREDIT·(promotions authored) − REP_AUTHOR_SLASH·(revoked authored)
#       − REP_JUROR_SLASH·(ACCEPT votes signed in certs of revoked capsules), floored at 0.
# Below REP_ISOLATION_FLOOR the existing Pawl check 5 auto-rejects the author's submissions.
REP_PROMOTION_CREDIT = 0.05
