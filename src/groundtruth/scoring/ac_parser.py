"""Deterministic Given/When/Then acceptance-criterion parser. Zero LLM.

A ticket's ACs are whatever G-W-T block its description carries; Intake
(Phase 4) writes ACs in exactly this shape, so the parser that scores a
ticket reads back what Intake wrote. Clause lines look like::

    Given: a page of 3 results
    When: the caller requests page 2
    Then: results 4-6 are returned

Each ``Given:`` starts a new criterion. A criterion missing any clause
(or with an empty one) is kept and marked malformed — it counts in the
ac_validity denominator as a failure, never silently dropped.
"""

from __future__ import annotations

import re

from groundtruth.contracts.story import AcceptanceCriterion

_CLAUSE = re.compile(r"^\s*(given|when|then)\s*[:\-]\s*(.*)$", re.IGNORECASE)


def parse_acceptance_criteria(jira_key: str, description: str) -> list[AcceptanceCriterion]:
    clauses: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for line in (description or "").splitlines():
        match = _CLAUSE.match(line)
        if match is None:
            continue
        keyword = match.group(1).lower()
        text = match.group(2).strip()

        if keyword == "given" or current is None:
            if current is not None:
                clauses.append(current)
            current = {"given": "", "when": "", "then": ""}
        if current[keyword]:
            # Duplicate clause keyword: close the partial criterion, start over.
            clauses.append(current)
            current = {"given": "", "when": "", "then": ""}
        current[keyword] = text

    if current is not None:
        clauses.append(current)

    criteria: list[AcceptanceCriterion] = []
    for index, clause in enumerate(clauses, start=1):
        raw = (
            f"Given: {clause['given']} When: {clause['when']} "
            f"Then: {clause['then']}"
        ).strip()
        criteria.append(
            AcceptanceCriterion(
                ac_id=f"{jira_key}#{index}",
                given=clause["given"],
                when=clause["when"],
                then=clause["then"],
                raw=raw,
                is_wellformed=bool(clause["given"] and clause["when"] and clause["then"]),
            )
        )
    return criteria
