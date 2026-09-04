"""Tests for GitHub/Jira URL parsers used by the Settings UI."""

from __future__ import annotations

import pytest

from groundtruth.connections.urls import parse_github_repo_url, parse_jira_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/acme/corp", ("acme", "corp")),
        ("https://github.com/acme/corp/pull/123", ("acme", "corp")),
        ("https://github.com/acme/corp/tree/main/src", ("acme", "corp")),
        ("git@github.com:acme/corp.git", ("acme", "corp")),
        ("https://github.com/acme/corp.git", ("acme", "corp")),
        ("ssh://git@github.com/acme/corp", ("acme", "corp")),
        ("https://notgithub.com/acme/corp", ("", "")),
        ("https://github.com/acme", ("", "")),
        ("", ("", "")),
    ],
)
def test_parse_github_repo_url(url: str, expected: tuple[str, str]) -> None:
    assert parse_github_repo_url(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://acme.atlassian.net/jira/software/projects/GT/boards/1",
            ("https://acme.atlassian.net", "GT"),
        ),
        (
            "https://acme.atlassian.net/jira/software/c/projects/GT/boards/1",
            ("https://acme.atlassian.net", "GT"),
        ),
        (
            "https://acme.atlassian.net/browse/GT-42",
            ("https://acme.atlassian.net", "GT"),
        ),
        (
            "https://acme.atlassian.net/secure/RapidBoard.jspa?projectKey=GT",
            ("https://acme.atlassian.net", "GT"),
        ),
        (
            "acme.atlassian.net/jira/software/projects/FOO/boards/2",
            ("https://acme.atlassian.net", "FOO"),
        ),
        ("https://acme.atlassian.net", ("https://acme.atlassian.net", "")),
        ("not a url", ("", "")),
    ],
)
def test_parse_jira_url(url: str, expected: tuple[str, str]) -> None:
    assert parse_jira_url(url) == expected
