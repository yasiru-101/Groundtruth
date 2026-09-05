"""Record/replay envelope: the single doorway to every external system.

Every outbound call — Jira REST, gh CLI, git reads, LLM hops — goes through
``Envelope.call`` with a ``RequestSpec``. Dispatch by run mode:

- LIVE: execute for real, persist nothing.
- RECORD: execute for real, persist the response payload under ``fixtures/``
  keyed by the sha256 of the canonical request.
- REPLAY: serve the recorded payload. A cache miss raises ``ReplayMiss`` —
  replay NEVER falls through to the network.

Fixture payloads are stored verbatim (redaction is applied to ledger entries,
not to the replay cache, so replayed data is byte-identical to recorded
data). The fixtures directory is gitignored; fixtures never leave the machine
that captured them.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from groundtruth.clock import Clock, SystemClock
from groundtruth.config import RunMode


class ReplayMiss(Exception):
    """REPLAY was asked for a request that was never recorded."""


class FixtureCorrupt(Exception):
    """A fixture file exists but cannot be parsed or fails its hash check."""


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass(frozen=True)
class RequestSpec:
    """A canonical description of one external call.

    ``url`` is an opaque label for non-HTTP backends (e.g. ``"git:log"``,
    ``"gh:pr_list"``) — anything stable and descriptive works.
    """

    method: str
    url: str
    params: dict[str, Any] | None = None
    body: Any = None

    def canonical(self) -> str:
        return json.dumps(
            {
                "method": self.method.upper(),
                "url": self.url,
                "params": _canonical(self.params or {}),
                "body": _canonical(self.body),
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def request_hash(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FixtureRecord:
    hash: str
    spec: RequestSpec
    payload: Any
    recorded_at: datetime


class FixtureStore:
    """Persists recorded payloads as ``<fixtures_dir>/<hash>.json``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def exists(self, key: str) -> bool:
        return self.path_for(key).exists()

    def write(self, record: FixtureRecord) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        doc = {
            "hash": record.hash,
            "spec": {
                "method": record.spec.method,
                "url": record.spec.url,
                "params": record.spec.params,
                "body": record.spec.body,
            },
            "recorded_at": record.recorded_at.isoformat(),
            "payload": record.payload,
        }
        target = self.path_for(record.hash)
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        os.replace(tmp, target)

    def read(self, key: str) -> FixtureRecord:
        path = self.path_for(key)
        if not path.exists():
            raise ReplayMiss(
                f"No fixture recorded for request hash {key} ({path}). "
                "Re-run in record mode to capture it."
            )
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise FixtureCorrupt(f"Cannot parse fixture {path}: {exc}") from exc
        if doc.get("hash") != key:
            raise FixtureCorrupt(
                f"Fixture {path} stores hash {doc.get('hash')!r}, expected {key!r}."
            )
        spec = RequestSpec(
            method=doc["spec"]["method"],
            url=doc["spec"]["url"],
            params=doc["spec"].get("params"),
            body=doc["spec"].get("body"),
        )
        return FixtureRecord(
            hash=key,
            spec=spec,
            payload=doc["payload"],
            recorded_at=datetime.fromisoformat(doc["recorded_at"]),
        )

    def keys(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.stem for p in self.root.glob("*.json"))


class Envelope:
    """Dispatches external calls by run mode."""

    def __init__(self, mode: RunMode, store: FixtureStore, clock: Clock | None = None) -> None:
        self._mode = mode
        self._store = store
        self._clock: Clock = clock or SystemClock()
        self._seen_recorded_at: datetime | None = None

    @property
    def mode(self) -> RunMode:
        return self._mode

    @property
    def store(self) -> FixtureStore:
        return self._store

    def call(self, spec: RequestSpec, live: Callable[[], Any]) -> Any:
        """Run ``live`` (LIVE/RECORD) or serve the fixture (REPLAY)."""
        key = spec.request_hash()

        if self.mode == RunMode.REPLAY:
            record = self._store.read(key)
            if self._seen_recorded_at is None:
                self._seen_recorded_at = record.recorded_at
            return record.payload

        payload = live()

        if self._mode is RunMode.RECORD:
            self._store.write(
                FixtureRecord(
                    hash=key,
                    spec=spec,
                    payload=payload,
                    recorded_at=self._clock.now(),
                )
            )
        return payload

    def replay_clock_hint(self) -> datetime | None:
        """Timestamp of the first replayed record — callers pin ``as_of`` to it.

        Only meaningful in REPLAY mode after at least one call.
        """
        return self._seen_recorded_at
