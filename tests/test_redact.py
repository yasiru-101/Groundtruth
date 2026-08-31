"""Tests for the redaction module.

Round-trip: secrets must be scrubbed, non-secrets must pass through.
"""

from __future__ import annotations

import pytest

from groundtruth.safety.redact import redact, redact_dict, redact_list

REAL_TOKENS = [
    ("gho_1234567890abcdefghijklmnopqrstuvwxyz", "GitHub OAuth"),
    ("ghp_1234567890abcdefghijklmnopqrstuvwxyz", "GitHub PAT"),
    ("ghs_1234567890abcdefghijklmnopqrstuvwxyz", "GitHub App installation"),
    ("ghr_1234567890abcdefghijklmnopqrstuvwxyz", "GitHub refresh"),
    ("ATATT3xFfGF0abcdefghijklmnopqrstuvwxyz", "Jira API token"),
]

JWT_SAMPLE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
BEARER_SAMPLE = "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ0ZXN0In0.abc123"


class TestRedact:
    @pytest.mark.parametrize("token,label", REAL_TOKENS)
    def test_token_patterns_redacted(self, token: str, label: str) -> None:
        text = f"My token is {token} and it works."
        result = redact(text)
        assert token not in result
        assert "[REDACTED]" in result

    def test_jwt_redacted(self) -> None:
        text = f"Authorization: {JWT_SAMPLE}"
        result = redact(text)
        assert JWT_SAMPLE not in result
        assert "[REDACTED]" in result

    def test_bearer_redacted(self) -> None:
        text = f"Authorization: {BEARER_SAMPLE}"
        result = redact(text)
        assert "Bearer" not in result or "eyJ" not in result
        assert "[REDACTED]" in result

    def test_non_secrets_pass_through(self) -> None:
        text = "The ticket AUTO-14 is in progress. Commit abc123 was merged."
        assert redact(text) == text

    def test_multiple_tokens_in_one_string(self) -> None:
        text = "ghp_1234567890abcdefghijklmnopqrstuvwxyz and ATATT3xFfGF0abcdefghijklmnopqrst"
        result = redact(text)
        assert "ghp_" not in result
        assert "ATATT" not in result
        assert result.count("[REDACTED]") == 2

    def test_empty_string(self) -> None:
        assert redact("") == ""

    def test_redact_dict(self) -> None:
        data = {
            "token": "ghp_1234567890abcdefghijklmnopqrstuvwxyz",
            "name": "AUTO-14",
            "nested": {"secret": "ATATT3xFfGF0abcdefghijklmnopqrst"},
        }
        result = redact_dict(data)
        assert "ghp_" not in result["token"]
        assert result["name"] == "AUTO-14"
        assert "ATATT" not in result["nested"]["secret"]

    def test_redact_list(self) -> None:
        data = ["ghp_1234567890abcdefghijklmnopqrstuvwxyz", "safe text", {"key": "ATATT3xFfGF0abcdefghijklmnopqrst"}]
        result = redact_list(data)
        assert "ghp_" not in result[0]
        assert result[1] == "safe text"
        assert "ATATT" not in result[2]["key"]

    def test_api_key_pattern_redacted(self) -> None:
        text = "api_key=sk_live_abcdefghijklmnop1234"
        result = redact(text)
        assert "sk_live" not in result
