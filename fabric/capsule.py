"""The Capsule: schema, canonicalization, content addressing, signing (BLUEPRINT §3, §4).

A Capsule is a proof-carrying unit of learned mitigation knowledge. Its identity is its content:
`capsule_id` is the SHA-256 of the canonical JSON of the *immutable body* only, so identical capsules
dedup for free and any tampering is evident (BLUEPRINT §3). The author `sig` covers that same
immutable body. `lifecycle` is mutable, node-local metadata — it is deliberately **excluded** from
both `capsule_id` and `sig`, and travels alongside the capsule in the store (BLUEPRINT §3 note,
binding decision M2.1).

Field names are verbatim from BLUEPRINT §3 — they are quoted in the defence, so they are API. This
module defines the schema and the pure identity/signing functions only. The lifecycle *transition*
machinery (Pawl, Jury, shadow staging) is M3; here `LifecycleState` is an enum and nothing more.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import BaseModel

from fabric import keyring as _keyring

# The seven immutable fields that constitute a capsule's content-addressed body (BLUEPRINT §3,
# binding decision M2.1). `capsule_id` and `sig` are derived from these; `lifecycle` is excluded.
IMMUTABLE_FIELDS: tuple[str, ...] = (
    "kind",
    "registry_version",
    "context",
    "payload",
    "claim",
    "evidence",
    "provenance",
)


class LifecycleState(str, Enum):
    """The ten capsule lifecycle states (BLUEPRINT §4).

    M2 defines the enum only. The transition machine (submit → Pawl → Jury → shadow → active, plus
    revoke/quarantine/expire) is built in M3/M5 — do not add transition logic here.
    """

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    REJECTED = "REJECTED"
    JURY = "JURY"
    CANDIDATE = "CANDIDATE"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    QUARANTINED = "QUARANTINED"


class Context(BaseModel):
    """Where a capsule applies. `dims` are intervals/sets over registry dimensions only; wildcard
    contexts are rejected by the Pawl (blast-radius bound, BLUEPRINT §3)."""

    incident_class: str
    dims: dict[str, object]


class Payload(BaseModel):
    """The mitigation. `rule` is a *typed action*, never code, never text — the Pawl reasons over it
    mechanically (BLUEPRINT §3)."""

    rule: dict[str, object]


class Claim(BaseModel):
    """The falsifiable statement. A capsule without a falsifiable claim is rejected at schema
    (BLUEPRINT §3)."""

    metric: str
    baseline_median: float
    with_capsule_median: float
    delta_pct: float
    n_episodes: int


class Evidence(BaseModel):
    """What makes the claim replayable by strangers — proof-carrying capsules (BLUEPRINT §3)."""

    scenario_seeds: list[int]
    conformance_required: list[str]
    trace_digest: str


class Provenance(BaseModel):
    """Authorship and the DAG edges that make Excision surgical and bisect possible (BLUEPRINT §3)."""

    author: str
    author_epoch: int
    derived_from: list[str]
    born_of_contract: str | None = None


class Lifecycle(BaseModel):
    """Mutable, node-local metadata: excluded from `capsule_id` and `sig` (binding decision M2.1).

    `quorum_cert` is `{jurors, votes, partition_view, sim_time}` once the Jury signs it (M3)."""

    state: LifecycleState
    quorum_cert: dict[str, object] | None = None
    confidence: float = 0.0
    created_at_sim: float = 0.0
    ttl_sim: float = 600.0


class Capsule(BaseModel):
    """A signed, content-addressed unit of mitigation knowledge (BLUEPRINT §3).

    `capsule_id` content-addresses the immutable body (dedup for free, tamper-evident, gossip by
    digest). `sig` is the author's HMAC over that same body. `lifecycle` rides alongside but is not
    part of the identity or the signature.
    """

    capsule_id: str
    kind: str
    registry_version: str
    context: Context
    payload: Payload
    claim: Claim
    evidence: Evidence
    provenance: Provenance
    lifecycle: Lifecycle
    sig: str


def canonical_body(capsule: Capsule) -> bytes:
    """Canonical JSON of the immutable body only: sorted keys, compact separators (BLUEPRINT §3).

    Excludes `capsule_id`, `sig`, and `lifecycle` — the content that identity and signature cover.
    """
    body = capsule.model_dump(mode="json", include=set(IMMUTABLE_FIELDS))
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_id(body: bytes) -> str:
    """The content address: SHA-256 hexdigest of the canonical body."""
    return hashlib.sha256(body).hexdigest()


def build_capsule(
    *,
    kind: str,
    registry_version: str,
    context: Context,
    payload: Payload,
    claim: Claim,
    evidence: Evidence,
    provenance: Provenance,
    lifecycle: Lifecycle,
    keyring=_keyring,
) -> Capsule:
    """Seal a capsule: compute its content address and the author's signature over the same body.

    The signing identity is `provenance.author` verbatim (e.g. `agent:site-a`). `lifecycle` is
    stored as given but does not affect `capsule_id` or `sig` (binding decision M2.1).
    """
    # Build once with placeholder id/sig so canonical_body can dump the immutable fields, then fill
    # in the derived id/sig. capsule_id/sig are excluded from the body, so the placeholders never
    # leak into what is hashed or signed.
    draft = Capsule(
        capsule_id="",
        kind=kind,
        registry_version=registry_version,
        context=context,
        payload=payload,
        claim=claim,
        evidence=evidence,
        provenance=provenance,
        lifecycle=lifecycle,
        sig="",
    )
    body = canonical_body(draft)
    draft.capsule_id = compute_id(body)
    draft.sig = keyring.sign(provenance.author, body)
    return draft


def check_integrity(capsule: Capsule, keyring=_keyring) -> tuple[bool, str]:
    """Tamper-evidence: recompute the content address and verify the author signature.

    Returns `(ok, reason)`; the reason names which check failed, in one user-facing line.

    # DECISION: named `check_integrity` to stay distinct from M3's `validate_capsule()` (the full
    # Pawl/Jury pipeline in fabric/pawl.py + fabric/jury.py). M2 only guarantees identity+signature
    # integrity; admission policy is M3's job.
    """
    body = canonical_body(capsule)
    expected_id = compute_id(body)
    if capsule.capsule_id != expected_id:
        return False, f"capsule_id mismatch: body hashes to {expected_id[:12]}, not {capsule.capsule_id[:12]}"
    if not keyring.verify(capsule.provenance.author, body, capsule.sig):
        return False, f"bad signature: not signed by {capsule.provenance.author}"
    return True, "ok"
