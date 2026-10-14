"""NVIDIA credential pool — loading, redaction and rate-limit rotation.

Two facts, both verified live on 2026-09-27, drive this design:

1. All 19 supplied ``nvapi-`` keys are VALID: each returned HTTP 200 on
   ``GET /v1/models`` and each sees the same 82-model catalogue.
2. The keys are ACCOUNT-scoped, not model-scoped. The key that shipped next to
   ``moonshotai/kimi-k3`` successfully invoked
   ``nvidia/nemotron-3-ultra-550b-a55b`` (HTTP 200, 2.7s).

Fact 2 is the useful one. NVIDIA's shared NIM workers reject with
``503 ResourceExhausted: Worker local total request limit reached (16/16)``
— observed twice on ``nemotron-3-nano-omni`` and once on ``laguna-xs`` at
(174/32). Because any key can drive any model, a 429/503 does not have to be a
user-visible failure: the client rotates to the next credential and retries.
That converts a hard per-key ceiling into a pooled one.

SECURITY
--------
* Keys are read from the environment ONLY. Nothing is hardcoded here, and
  ``.env.nvidia`` is matched by the repository's existing ``.env.*``
  gitignore rule (verified with ``git check-ignore``).
* ``redact()`` is the only sanctioned way to put a key near a log line. The
  raw value never enters a log record, an exception message, or an API
  response — ``__repr__`` is overridden so an accidental f-string cannot leak
  the pool either.
* Production must inject these as platform secrets (Vercel / Modal / CI).
  ``.env.nvidia`` is a local-development convenience and is never deployed.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

#: Env var carrying the credential for each registry slot, in the order the
#: keys were supplied. Order matters only for deterministic rotation.
SLOT_KEY_ENV_VARS: List[str] = [
    "NVIDIA_KEY_NEMOTRON_3_ULTRA_550B_A55B",
    "NVIDIA_KEY_NEMOTRON_3_SUPER_120B_A12B",
    "NVIDIA_KEY_NEMOTRON_3_5_LIGHTNING_30B_A3B",
    "NVIDIA_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B_REASONING",
    "NVIDIA_KEY_NEMOTRON_3_5_CONTENT_SAFETY",
    "NVIDIA_KEY_NEMOTRON_3_EMBED_1B",
    "NVIDIA_KEY_RIVA_TRANSLATE_4B_INSTRUCT_V2",
    "NVIDIA_KEY_KIMI_K3",
    "NVIDIA_KEY_GLM_5_3",
    "NVIDIA_KEY_GLM_5_3_FLASH",
    "NVIDIA_KEY_DIFFUSIONGEMMA_26B_A4B_IT",
    "NVIDIA_KEY_GEMMA_4_31B_IT",
    "NVIDIA_KEY_MUSE_GLIMMER_30B",
    "NVIDIA_KEY_DEEPSEEK_V4_1_FLASH",
    "NVIDIA_KEY_LAGUNA_XS_2_1",
    "NVIDIA_KEY_KUMO_RELATIONAL",
    "NVIDIA_KEY_NEMOTRON_VOICECHAT",
    "NVIDIA_KEY_ISING_CALIBRATION_1_5_31B",
    "NVIDIA_KEY_ISING_CALIBRATION_1_5_31B_2",
]

#: Legacy names already consumed by orchestrator.py / ai_readiness.py. Kept so
#: the pool is a superset of the existing contract rather than a replacement.
LEGACY_KEY_ENV_VARS: List[str] = ["NVIDIA_API_KEY", "NVIDIA_CHAT_KEY_2"]

#: MEASURED 2026-10-14. An operator env file names the per-model keys after the
#: PLATFORM credential (`NVIDIA_API_KEY_KIMI_K3`); this repo names the SLOT
#: (`NVIDIA_KEY_KIMI_K3`). Both are correct and neither is worth a rename: a
#: slot whose key exists under a name the pool never reads is a slot the product
#: does not have. Without this table, a file holding nineteen live keys reported
#: `slots_missing: 19`, the stylist fell through to a provider it was not meant
#: to use, and `/health` called NVIDIA unconfigured.
#:
#: Names that follow the mechanical rule are derived; the four below do not
#: (the supply distinguished two keys for one model by suffix, and abbreviated
#: two model names), so they are listed rather than guessed.
SLOT_KEY_ENV_ALIASES: Dict[str, Tuple[str, ...]] = {
    "NVIDIA_KEY_ISING_CALIBRATION_1_5_31B": ("NVIDIA_API_KEY_ISING_CALIBRATION_A",),
    "NVIDIA_KEY_ISING_CALIBRATION_1_5_31B_2": ("NVIDIA_API_KEY_ISING_CALIBRATION_B",),
    "NVIDIA_KEY_DIFFUSIONGEMMA_26B_A4B_IT": ("NVIDIA_API_KEY_DIFFUSIONGEMMA_26B_A4B",),
    "NVIDIA_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B_REASONING": ("NVIDIA_API_KEY_NEMOTRON_3_NANO_OMNI_30B_A3B",),
}


def alias_env_names(slot: str) -> Tuple[str, ...]:
    """Every accepted alternate name for one slot var, in precedence order.

    The canonical name always wins (it is tried first by :meth:`_discover`), so
    an explicit rename in a deployment still behaves exactly as it did.
    """
    names: List[str] = []
    if slot.startswith("NVIDIA_KEY_"):
        names.append("NVIDIA_API_KEY_" + slot[len("NVIDIA_KEY_"):])
    names.extend(SLOT_KEY_ENV_ALIASES.get(slot, ()))
    return tuple(dict.fromkeys(name for name in names if name != slot))

_KEY_PREFIX = "nvapi-"
_DOTENV_CANDIDATES = (".env.nvidia", "backend/.env", ".env")


def redact(key: Optional[str]) -> str:
    """Render a credential safe for logs: ``nvapi-AbCd...wxyz``.

    Shows enough to correlate an incident with a slot, never enough to use.
    """
    if not key:
        return "<unset>"
    if len(key) <= 16:
        return "<redacted>"
    return f"{key[:10]}...{key[-4:]}"


def _repo_root() -> Path:
    # providers/nvidia/keypool.py -> providers -> app -> backend -> repo root
    return Path(__file__).resolve().parents[4]


def _load_dotenv_values() -> Dict[str, str]:
    """Parse the dev dotenv files WITHOUT mutating ``os.environ``.

    Real process environment always wins, so a deployed platform secret can
    never be shadowed by a stray file that got copied into an image.
    """
    # Hermetic tests: `conftest.py` sets CONFIT_IGNORE_DOTENV=1 before importing
    # anything, and this loader must honour it exactly like Settings does.
    #
    # MEASURED 2026-09-27: this pool reads the dotenv files DIRECTLY rather than
    # through Settings, so it stayed configured even after the suite was made
    # hermetic — which left the wardrobe moderation gate making real, billed
    # NVIDIA calls during pytest and turned upload tests red. A credential
    # loader that ignores the test contract is a credential loader that will
    # eventually spend money in CI.
    values: Dict[str, str] = {}
    if os.environ.get("CONFIT_IGNORE_DOTENV") == "1":
        return values
    root = _repo_root()
    for name in _DOTENV_CANDIDATES:
        path = root / name
        try:
            if not path.is_file():
                continue
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                # First file wins; earlier candidates are higher precedence.
                if k and v and k not in values:
                    values[k] = v
        except OSError:
            # An unreadable dev file must never break boot.
            continue
    return values


class NvidiaKeyPool:
    """Thread-safe rotating pool of NVIDIA credentials.

    Not a load balancer: ``preferred_key`` is honoured first so each model
    normally uses the credential it shipped with (clean per-model usage
    accounting). Rotation only happens when a call is rejected for capacity.
    """

    def __init__(self, keys: Optional[Dict[str, str]] = None) -> None:
        self._lock = threading.Lock()
        self._cursor = 0
        self._alias_sources: Dict[str, str] = {}
        self._keys: Dict[str, str] = keys if keys is not None else self._discover()

    # ── discovery ────────────────────────────────────────────────────────────

    def _discover(self) -> Dict[str, str]:
        dotenv = _load_dotenv_values()
        found: Dict[str, str] = {}
        sources: Dict[str, str] = {}
        for name in SLOT_KEY_ENV_VARS + LEGACY_KEY_ENV_VARS:
            value = os.environ.get(name) or dotenv.get(name)
            if not value:
                for alias in alias_env_names(name):
                    value = os.environ.get(alias) or dotenv.get(alias)
                    if value:
                        sources[name] = alias
                        break
            if value and value.startswith(_KEY_PREFIX):
                found[name] = value
        self._alias_sources = sources
        return found

    def reload(self) -> None:
        """Re-read the environment — used by tests and by key rotation."""
        with self._lock:
            self._keys = self._discover()
            self._cursor = 0

    def alias_sources(self) -> Dict[str, str]:
        """slot var -> the alternate env name that actually supplied it.

        Diagnostics only. A deployment that reads this and finds entries is one
        whose file names differ from the repo's; it is working, and the mapping
        is what proves where each credential came from.
        """
        return dict(self._alias_sources)

    # ── state ────────────────────────────────────────────────────────────────

    @property
    def configured(self) -> bool:
        return bool(self._unique_keys())

    def _unique_keys(self) -> List[str]:
        """Distinct credentials, stable order. Two env names may hold the same
        value (``NVIDIA_API_KEY`` aliases a slot key), and retrying the same
        exhausted credential twice would waste the retry budget."""
        seen: List[str] = []
        for name in SLOT_KEY_ENV_VARS + LEGACY_KEY_ENV_VARS:
            value = self._keys.get(name)
            if value and value not in seen:
                seen.append(value)
        return seen

    def slot(self, env_name: Optional[str]) -> Optional[str]:
        """The credential registered for one registry slot, if present."""
        if not env_name:
            return None
        return self._keys.get(env_name)

    def size(self) -> int:
        return len(self._unique_keys())

    # ── rotation ─────────────────────────────────────────────────────────────

    def candidates(self, preferred_key_env: Optional[str] = None,
                   limit: Optional[int] = None) -> Iterator[str]:
        """Yield credentials to try, in order.

        The slot's own key goes first (accounting stays clean), then the rest
        of the pool from a rotating cursor so concurrent workers do not all
        stampede the same second credential.
        """
        keys = self._unique_keys()
        if not keys:
            return

        ordered: List[str] = []
        preferred = self.slot(preferred_key_env)
        if preferred:
            ordered.append(preferred)

        with self._lock:
            start = self._cursor
            self._cursor = (self._cursor + 1) % len(keys)

        for i in range(len(keys)):
            key = keys[(start + i) % len(keys)]
            if key not in ordered:
                ordered.append(key)

        if limit is not None:
            ordered = ordered[:limit]
        yield from ordered

    # ── observability ────────────────────────────────────────────────────────

    def status(self) -> Dict[str, object]:
        """Credential-free snapshot for /health and diagnostics."""
        return {
            "configured": self.configured,
            "pool_size": self.size(),
            "slots_present": sorted(n for n in self._keys if n in SLOT_KEY_ENV_VARS),
            "slots_missing": sorted(n for n in SLOT_KEY_ENV_VARS if n not in self._keys),
            "legacy_present": sorted(n for n in self._keys if n in LEGACY_KEY_ENV_VARS),
            # Credential-free: names only, never values. Present so a rename in
            # an operator's file is visible in /health instead of invisible.
            "aliased_slots": dict(sorted(self._alias_sources.items())),
        }

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"<NvidiaKeyPool size={self.size()} configured={self.configured}>"

    __str__ = __repr__


#: Process-wide pool. Import this, do not build your own.
key_pool = NvidiaKeyPool()
