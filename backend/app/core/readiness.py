"""The health / readiness contract, in one place.

Gaps G-08 and G-09 are two halves of the same mistake: one endpoint was asked
to answer two different questions, so it answered neither honestly.

* As a **public** endpoint it published the platform's provider inventory, its
  storage provider and the environment variables needed to change it, the VTON
  engine's licence and fork provenance, and the schema's missing tables and
  columns. That is a reconnaissance summary handed to anyone who asks.
* As a **readiness** signal it reported ``status: healthy`` while
  ``storage.production_grade`` was ``false`` and ``storage.writable`` was
  ``false`` — every upload on the platform was broken, and the one field an
  operator or monitor reads said everything was fine.

So the two questions are separated and each is given a testable meaning:

``status`` — **liveness scope.** Can this process serve traffic? It depends
only on things that stop the service answering at all: the database reachable
and the schema the code requires actually present. It says nothing about
whether every advertised feature works.

``ready`` — **capability scope.** Can the platform do everything it advertises?
Computed from named capabilities, each with a criticality. A ``core``
capability that is ``blocked`` makes ``ready`` false and is named in
``blocking_capabilities``, so a broken upload path can never hide behind a
green liveness status again.

The four capability states are deliberately small and mutually exclusive:

``ready``       probed, working.
``degraded``    working, but not at production quality or on a fallback path.
``blocked``     not working. A core capability in this state sets ready=false.
``not_probed``  no probe exists. This is an honest gap, never a silent "ok" —
                an endpoint that cannot check something must say so rather
                than assert a value it never measured.

Nothing here performs I/O. Probes live in the service layer and hand their
verdicts in, which keeps the contract pure and unit-testable without a
database, a bucket or a network.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List

__all__ = [
    "STATUS_HEALTHY",
    "STATUS_DEGRADED",
    "STATUS_UNHEALTHY",
    "STATE_READY",
    "STATE_DEGRADED",
    "STATE_BLOCKED",
    "STATE_NOT_PROBED",
    "CRITICALITY_CORE",
    "CRITICALITY_SUPPORTING",
    "Capability",
    "summarise_capabilities",
    "liveness_status",
    "CONTRACT",
]

STATUS_HEALTHY = "healthy"
STATUS_DEGRADED = "degraded"
STATUS_UNHEALTHY = "unhealthy"

STATE_READY = "ready"
STATE_DEGRADED = "degraded"
STATE_BLOCKED = "blocked"
STATE_NOT_PROBED = "not_probed"

CRITICALITY_CORE = "core"
CRITICALITY_SUPPORTING = "supporting"

#: Published with the payload so the contract is self-describing instead of
#: living in a document nobody reads at 3am.
CONTRACT = {
    "status": (
        "liveness scope — can this process serve traffic? Depends only on the "
        "database being reachable and the schema this code requires being "
        "present. It does NOT mean every advertised feature works."
    ),
    "ready": (
        "capability scope — can the platform do everything it advertises? "
        "False when any core capability is blocked OR not probed; UNKNOWN is "
        "not READY. See blocking_capabilities and unprobed_capabilities."
    ),
    "states": {
        STATE_READY: "probed and working",
        STATE_DEGRADED: "working, but not at production quality or on a fallback path",
        STATE_BLOCKED: "not working; a core capability in this state sets ready=false",
        STATE_NOT_PROBED: (
            "no current measurement exists — an honest gap, never a silent ok; "
            "blocks readiness when the capability is core"
        ),
    },
    "criticality": {
        CRITICALITY_CORE: "blocking: the platform cannot deliver its product without it",
        CRITICALITY_SUPPORTING: "non-blocking: impairment is reported but does not set ready=false",
    },
}


@dataclass(frozen=True)
class Capability:
    """One advertised capability and what its probe actually found."""

    name: str
    state: str
    criticality: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.state not in (STATE_READY, STATE_DEGRADED, STATE_BLOCKED, STATE_NOT_PROBED):
            raise ValueError(f"unknown capability state {self.state!r}")
        if self.criticality not in (CRITICALITY_CORE, CRITICALITY_SUPPORTING):
            raise ValueError(f"unknown criticality {self.criticality!r}")

    def as_dict(self) -> Dict[str, str]:
        return {
            "state": self.state,
            "criticality": self.criticality,
            "detail": self.detail,
        }


def summarise_capabilities(capabilities: Iterable[Capability]) -> Dict[str, object]:
    """Reduce probed capabilities to the readiness verdict.

    ``ready`` is false for a **core** capability that is either ``blocked``
    OR ``not_probed``. UNKNOWN is not READY: if the platform cannot measure a
    core promise, it cannot truthfully claim that promise is ready. A
    supporting ``not_probed`` capability remains non-blocking but is always
    named in ``unprobed_capabilities``.
    """
    items: List[Capability] = list(capabilities)
    blocking = sorted(
        c.name for c in items
        if c.criticality == CRITICALITY_CORE
        and c.state in (STATE_BLOCKED, STATE_NOT_PROBED)
    )
    degraded = sorted(
        c.name for c in items
        if c.state == STATE_DEGRADED or (
            c.criticality == CRITICALITY_SUPPORTING and c.state == STATE_BLOCKED
        )
    )
    unprobed = sorted(c.name for c in items if c.state == STATE_NOT_PROBED)
    return {
        "ready": not blocking,
        "blocking_capabilities": blocking,
        "degraded_capabilities": degraded,
        "unprobed_capabilities": unprobed,
        "capabilities": {c.name: c.as_dict() for c in items},
    }


def liveness_status(database_ok: bool, schema_acceptable: bool) -> str:
    """The ``status`` field: liveness scope only.

    Unhealthy means the service cannot do its job at all. A capability being
    blocked is reported through ``ready``, not by darkening this field — mixing
    the two is what let a broken upload path read as "healthy" before.
    """
    if not database_ok:
        return STATUS_UNHEALTHY
    if not schema_acceptable:
        return STATUS_DEGRADED
    return STATUS_HEALTHY
