"""Safety checks for LLM-authored acceptance tests."""

from __future__ import annotations

import json

import pytest

from groundtruth.contracts.story import AcceptanceCriterion
from groundtruth.delivery.test_author import AuthoringError, author_tests


class FakeLLM:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def complete(self, *args, **kwargs) -> str:
        return json.dumps(self.payload)


def _criteria() -> list[AcceptanceCriterion]:
    return [
        AcceptanceCriterion(
            ac_id="AUTO-1#1",
            given="a feature",
            when="it is delivered",
            then="it works",
            raw="Given: a feature When: it is delivered Then: it works",
        )
    ]


def _payload(test_file: str, node_id: str) -> dict:
    return {
        "test_file": test_file,
        "content": "def test_feature():\n    assert value == 1\n",
        "bindings": [{"ac_id": "AUTO-1#1", "test_node_id": node_id}],
    }


class TestAuthoringPaths:
    def test_refuses_path_that_escapes_tests_directory(self, tmp_path) -> None:
        payload = _payload("tests/../src/escape.py", "tests/../src/escape.py::test_feature")

        with pytest.raises(AuthoringError, match="under workspace/tests"):
            author_tests(
                FakeLLM(payload),
                "AUTO-1",
                "summary",
                "description",
                _criteria(),
                tmp_path,
            )

        assert not (tmp_path / "src" / "escape.py").exists()

    def test_refuses_binding_to_a_different_test_file(self, tmp_path) -> None:
        payload = _payload("tests/test_new.py", "tests/test_existing.py::test_feature")

        with pytest.raises(AuthoringError, match="does not match authored test file"):
            author_tests(
                FakeLLM(payload),
                "AUTO-1",
                "summary",
                "description",
                _criteria(),
                tmp_path,
            )

        assert not (tmp_path / "tests" / "test_new.py").exists()

    def test_writes_only_a_new_bound_test_file(self, tmp_path) -> None:
        payload = _payload("tests/test_new.py", "tests/test_new.py::test_feature")

        authored = author_tests(
            FakeLLM(payload),
            "AUTO-1",
            "summary",
            "description",
            _criteria(),
            tmp_path,
        )

        assert authored.test_file == "tests/test_new.py"
        assert (tmp_path / authored.test_file).exists()
