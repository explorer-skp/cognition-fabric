"""Per-agent signing keyring (BLUEPRINT §3 signing note, §13 honest scoping).

Signing in the prototype is HMAC with per-agent keys from a local keyring. This is a *stub for real
PKI with the same interface*: Phase 1 already specified the identity layer, and the upgrade to real
asymmetric keys is a drop-in at these three functions (BLUEPRINT §13). Everything here is pure and
deterministic — no I/O, no wall-clock, no module-level randomness — so a capsule's `sig` is
byte-stable across runs and machines.
"""

from __future__ import annotations

import hashlib
import hmac

# DECISION: dev keys are derived deterministically from the agent identity string via a domain-
# separated SHA-256. This is the documented stub (BLUEPRINT §13); a real deployment swaps these
# three functions for asymmetric PKI without changing any caller — the interface is the contract.
_KEY_DOMAIN = b"cognition-fabric/dev-key/v1:"


def key_for(identity: str) -> bytes:
    """The secret HMAC key for an identity (e.g. `agent:site-a`). Deterministic per identity."""
    return hashlib.sha256(_KEY_DOMAIN + identity.encode("utf-8")).digest()


def sign(identity: str, body: bytes) -> str:
    """HMAC-SHA256 hexdigest of `body` under `identity`'s key. `body` is the canonical capsule body."""
    return hmac.new(key_for(identity), body, hashlib.sha256).hexdigest()


def verify(identity: str, body: bytes, sig: str) -> bool:
    """True iff `sig` is a valid signature by `identity` over `body`. Constant-time comparison."""
    expected = sign(identity, body)
    return hmac.compare_digest(expected, sig)
