"""Loader for the frozen scoring policy.

``scoring_policy.yaml`` is frozen in Phase 3; this module only reads and
validates it. ``policy_hash`` is the sha256 of the raw file bytes, so any
edit (even whitespace) produces a different hash and a different
``policy_version`` must be declared.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from groundtruth.config import PROJECT_ROOT

POLICY_PATH = PROJECT_ROOT / "scoring_policy.yaml"

DIMENSION_NAMES = (
    "ac_validity",
    "progress_integrity",
    "done_integrity",
    "staleness_health",
    "duplication_health",
)


class PolicyError(Exception):
    pass


class ScoringPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str
    policy_hash: str
    weights: dict[str, float]
    staleness_window_days: int
    stale_day_cap: int
    duplicate_threshold: float
    token_min_length: int
    source_path: str = ""

    def weight(self, dimension: str) -> float:
        try:
            return self.weights[dimension]
        except KeyError as exc:
            raise PolicyError(
                f"Policy {self.policy_version} has no weight for {dimension!r}."
            ) from exc


class _RawPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str
    staleness: dict[str, int]
    duplicate: dict[str, float | int]
    dimensions: dict[str, dict[str, float]]


def load_policy(path: Path | None = None) -> ScoringPolicy:
    policy_path = path or POLICY_PATH
    if not policy_path.exists():
        raise PolicyError(f"Scoring policy not found at {policy_path}.")

    raw_bytes = policy_path.read_bytes()
    try:
        doc = yaml.safe_load(raw_bytes.decode("utf-8"))
    except yaml.YAMLError as exc:
        raise PolicyError(f"Scoring policy {policy_path} is not valid YAML: {exc}") from exc

    try:
        raw = _RawPolicy.model_validate(doc)
    except Exception as exc:
        raise PolicyError(f"Scoring policy {policy_path} is malformed: {exc}") from exc

    weights = {name: spec["weight"] for name, spec in raw.dimensions.items()}
    missing = set(DIMENSION_NAMES) - set(weights)
    extra = set(weights) - set(DIMENSION_NAMES)
    if missing or extra:
        raise PolicyError(
            f"Policy must define exactly {sorted(DIMENSION_NAMES)}; "
            f"missing={sorted(missing)} extra={sorted(extra)}."
        )

    weight_sum = round(sum(weights.values()), 6)
    if weight_sum != 1.0:
        raise PolicyError(
            f"Dimension weights must sum to 1.0, got {weight_sum} "
            f"({ {k: v for k, v in sorted(weights.items())} })."
        )

    try:
        window = int(raw.staleness["window_days"])
        cap = int(raw.staleness["stale_day_cap"])
        threshold = float(raw.duplicate["similarity_threshold"])
        token_min = int(raw.duplicate["token_min_length"])
    except KeyError as exc:
        raise PolicyError(f"Scoring policy missing key {exc}.") from exc

    if window <= 0 or cap <= 0:
        raise PolicyError("staleness window_days and stale_day_cap must be positive.")
    if not 0.0 < threshold <= 1.0:
        raise PolicyError("duplicate similarity_threshold must be in (0, 1].")
    if token_min < 1:
        raise PolicyError("duplicate token_min_length must be >= 1.")

    return ScoringPolicy(
        policy_version=raw.policy_version,
        policy_hash=hashlib.sha256(raw_bytes).hexdigest(),
        weights=weights,
        staleness_window_days=window,
        stale_day_cap=cap,
        duplicate_threshold=threshold,
        token_min_length=token_min,
        source_path=str(policy_path),
    )
