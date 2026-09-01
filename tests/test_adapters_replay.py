"""Record → replay round-trips and the never-touch-network guarantee.

The core promise under test: once a call is recorded, REPLAY serves it
without ever invoking the live callable, and an unrecorded call raises
ReplayMiss instead of falling through to the network.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from groundtruth.adapters.base import (
    Envelope,
    FixtureCorrupt,
    FixtureRecord,
    FixtureStore,
    ReplayMiss,
    RequestSpec,
)
from groundtruth.adapters.gitlog import _FORMAT, _REC, _SEP, GitLog
from groundtruth.adapters.github import GitHubClient
from groundtruth.adapters.jira import JiraClient
from groundtruth.adapters.llm import LLMClient, LLMError, PromptName
from groundtruth.config import RunMode, Settings


def make_settings() -> Settings:
    return Settings(
        jira_base_url="https://jira.example",
        jira_email="t@example.com",
        jira_api_token="tok",
        github_repo_owner="acme",
        github_repo_name="demo",
        llm_api_key="k",
        llm_model="m",
        llm_base_url="https://llm.example",
    )


class TestRequestSpec:
    def test_hash_stable_across_param_key_order(self) -> None:
        a = RequestSpec("POST", "/x", params={"b": 1, "a": 2}, body=None)
        b = RequestSpec("POST", "/x", params={"a": 2, "b": 1}, body=None)
        assert a.request_hash() == b.request_hash()

    def test_hash_changes_with_body(self) -> None:
        a = RequestSpec("POST", "/x", body={"page": 1})
        b = RequestSpec("POST", "/x", body={"page": 2})
        assert a.request_hash() != b.request_hash()

    def test_hash_changes_with_url(self) -> None:
        assert (
            RequestSpec("GET", "/a").request_hash()
            != RequestSpec("GET", "/b").request_hash()
        )

    def test_hash_ignores_method_case(self) -> None:
        assert (
            RequestSpec("get", "/x").request_hash()
            == RequestSpec("GET", "/x").request_hash()
        )


class TestFixtureStore:
    def test_write_read_round_trip(self, tmp_path: Path) -> None:
        store = FixtureStore(tmp_path)
        spec = RequestSpec("GET", "/rest/api/3/issue/AUTO-1")
        record = FixtureRecord(
            hash=spec.request_hash(),
            spec=spec,
            payload={"key": "AUTO-1"},
            recorded_at=datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc),
        )
        store.write(record)
        assert store.keys() == [spec.request_hash()]

        loaded = store.read(spec.request_hash())
        assert loaded.payload == {"key": "AUTO-1"}
        assert loaded.spec == spec
        assert loaded.recorded_at == record.recorded_at

    def test_read_missing_raises_replay_miss(self, tmp_path: Path) -> None:
        store = FixtureStore(tmp_path)
        with pytest.raises(ReplayMiss):
            store.read("deadbeef")

    def test_read_tampered_hash_raises_fixture_corrupt(self, tmp_path: Path) -> None:
        path = tmp_path / "abc123.json"
        path.write_text(json.dumps({"hash": "other", "payload": {}}), encoding="utf-8")
        with pytest.raises(FixtureCorrupt):
            FixtureStore(tmp_path).read("abc123")

    def test_read_unparsable_raises_fixture_corrupt(self, tmp_path: Path) -> None:
        (tmp_path / "abc123.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(FixtureCorrupt):
            FixtureStore(tmp_path).read("abc123")


class TestEnvelope:
    def test_live_calls_live_and_persists_nothing(self, tmp_path: Path) -> None:
        store = FixtureStore(tmp_path)
        envelope = Envelope(mode=RunMode.LIVE, store=store)
        calls: list[int] = []

        result = envelope.call(
            RequestSpec("GET", "/x"), lambda: calls.append(1) or "payload"
        )
        assert result == "payload"
        assert calls == [1]
        assert store.keys() == []

    def test_record_calls_live_and_persists(self, tmp_path: Path) -> None:
        store = FixtureStore(tmp_path)
        envelope = Envelope(mode=RunMode.RECORD, store=store)
        spec = RequestSpec("GET", "/x")

        result = envelope.call(spec, lambda: {"answer": 42})
        assert result == {"answer": 42}
        assert store.exists(spec.request_hash())
        assert store.read(spec.request_hash()).payload == {"answer": 42}

    def test_replay_serves_fixture_without_calling_live(self, tmp_path: Path) -> None:
        spec = RequestSpec("GET", "/x")
        FixtureStore(tmp_path).write(
            FixtureRecord(
                hash=spec.request_hash(),
                spec=spec,
                payload={"answer": 42},
                recorded_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
            )
        )
        envelope = Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path))

        def live() -> Any:
            raise AssertionError("network was touched during replay")

        assert envelope.call(spec, live) == {"answer": 42}

    def test_replay_miss_propagates(self, tmp_path: Path) -> None:
        envelope = Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path))
        with pytest.raises(ReplayMiss):
            envelope.call(RequestSpec("GET", "/never-recorded"), lambda: "x")

    def test_replay_clock_hint_pins_first_record(
        self, tmp_path: Path
    ) -> None:
        store = FixtureStore(tmp_path)
        first = datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc)
        second = datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc)
        for url, when in (("/a", first), ("/b", second)):
            spec = RequestSpec("GET", url)
            store.write(
                FixtureRecord(
                    hash=spec.request_hash(),
                    spec=spec,
                    payload=None,
                    recorded_at=when,
                )
            )

        envelope = Envelope(mode=RunMode.REPLAY, store=store)
        assert envelope.replay_clock_hint() is None
        envelope.call(RequestSpec("GET", "/b"), lambda: "x")
        envelope.call(RequestSpec("GET", "/a"), lambda: "x")
        assert envelope.replay_clock_hint() == second


class StubGuard:
    allowed_remote = ""

    def __init__(
        self,
        stdout: str = "",
        returncode: int = 0,
        script: dict[str, str] | None = None,
    ) -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.script = script or {}
        self.calls: list[list[str]] = []

    def _stdout_for(self, args: list[str]) -> str:
        for key, out in self.script.items():
            if key in args:
                return out
        return self.stdout

    def run(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
        env_extra: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        if self.returncode != 0:
            raise subprocess.CalledProcessError(
                self.returncode, args, stderr="stub failure"
            )
        return subprocess.CompletedProcess(
            args, 0, stdout=self._stdout_for(args), stderr=""
        )

    def run_gh(
        self, args: list[str], check: bool = True, capture_output: bool = True
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        if self.returncode != 0:
            raise subprocess.CalledProcessError(
                self.returncode, args, stderr="stub failure"
            )
        return subprocess.CompletedProcess(
            args, 0, stdout=self._stdout_for(args), stderr=""
        )


def _git_log_raw(rows: list[tuple[str, ...]]) -> str:
    return _REC.join(_SEP.join(row) for row in rows)


_LOG_ROWS = [
    ("c2", "2026-08-06T09:00:00+00:00", "2026-08-06T09:00:00+00:00", "S", "s@x", "wip: two", "c1"),
    ("c1", "2026-08-05T09:00:00+00:00", "2026-08-05T09:00:00+00:00", "S", "s@x", "wip: one", ""),
]
_MERGE_ROWS = [
    ("m1", "2026-08-07T09:00:00+00:00", "2026-08-07T09:00:00+00:00", "S", "s@x", "merge", "c2 c0"),
]


class TestGitLogReplay:
    def test_record_then_replay_without_guard(self, tmp_path: Path) -> None:
        guard = StubGuard(
            script={
                "feature/AUTO-1": _git_log_raw(_LOG_ROWS),
                "c0..main": _git_log_raw(_MERGE_ROWS),
            }
        )
        envelope = Envelope(mode=RunMode.RECORD, store=FixtureStore(tmp_path))
        gitlog = GitLog(envelope, guard)

        recorded = gitlog.commits("feature/AUTO-1")
        assert [c["sha"] for c in recorded] == ["c2", "c1"]
        assert recorded[1]["author_date"] == "2026-08-05T09:00:00+00:00"
        assert recorded[0]["is_merge"] is False
        recorded_merges = gitlog.commits("main", merges_only=True, base="c0")
        assert [c["sha"] for c in recorded_merges] == ["m1"]

        replay_guard = StubGuard()
        replay_guard.run = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("guard invoked during replay")
        )
        replay = Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path))
        replayed = GitLog(replay, replay_guard).commits("feature/AUTO-1")
        assert replayed == recorded

        merges = GitLog(replay, replay_guard).commits(
            "main", merges_only=True, base="c0"
        )
        assert [c["sha"] for c in merges] == ["m1"]
        assert merges[0]["is_merge"] is True
        assert merges[0]["parents"] == ["c2", "c0"]

    def test_replay_miss_when_never_recorded(self, tmp_path: Path) -> None:
        gitlog = GitLog(
            Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path)), StubGuard()
        )
        with pytest.raises(ReplayMiss):
            gitlog.branches()


class TestGitHubReplay:
    def test_pr_list_record_then_replay(self, tmp_path: Path) -> None:
        payload = [{"number": 7, "state": "MERGED", "headRefName": "feature/AUTO-2"}]
        guard = StubGuard(stdout=json.dumps(payload))
        guard.allowed_remote = "acme/demo"
        envelope = Envelope(mode=RunMode.RECORD, store=FixtureStore(tmp_path))
        client = GitHubClient(make_settings(), envelope, guard)  # type: ignore[arg-type]

        assert client.pr_list() == payload
        assert guard.calls

        replay_guard = StubGuard()
        replay_guard.run_gh = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("gh invoked during replay")
        )
        replay_client = GitHubClient(
            make_settings(),
            Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path)),
            replay_guard,  # type: ignore[arg-type]
        )
        assert replay_client.pr_list() == payload

    def test_replay_miss_when_never_recorded(self, tmp_path: Path) -> None:
        envelope = Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path))
        client = GitHubClient(make_settings(), envelope, StubGuard())  # type: ignore[arg-type]
        with pytest.raises(ReplayMiss):
            client.pr_view(7)


class TestJiraAndLLMReplay:
    def test_jira_replay_miss_without_credentials(self, tmp_path: Path) -> None:
        settings = Settings()  # no creds needed in replay
        envelope = Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path))
        client = JiraClient(settings, envelope, client=httpx.Client())
        with pytest.raises(ReplayMiss):
            client.get_issue("AUTO-1")

    def test_llm_replay_miss(self, tmp_path: Path) -> None:
        envelope = Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path))
        client = LLMClient(make_settings(), envelope, client=httpx.Client())
        with pytest.raises(ReplayMiss):
            client.complete(PromptName.INTAKE_DECOMPOSE, {"notes": "x"})

    def test_llm_prompt_registry_is_closed(self, tmp_path: Path) -> None:
        envelope = Envelope(mode=RunMode.REPLAY, store=FixtureStore(tmp_path))
        client = LLMClient(make_settings(), envelope, client=httpx.Client())
        with pytest.raises(LLMError, match="closed"):
            client.complete("not_a_prompt", {})
