"""The UNVERIFIED family: tickets claiming things their tests cannot prove.

Three deliberately split rules: seeded legacy tickets have no AC->test
binding because no Delivery Agent ever ran on them, so a single detector
would flag 100% of the board. NO_MAPPING is a coverage baseline;
MAPPING_STALE and TEST_FAILING are per-ticket defects.
"""

from __future__ import annotations

from factories import (
    ac,
    board,
    frozen_clock,
    repo,
    ticket,
    trace,
    trace_link,
)

from groundtruth.contracts.discrepancy import (
    ActionVerb,
    DiscrepancySeverity,
    DiscrepancyType,
)
from groundtruth.contracts.evidence import EvidenceKind
from groundtruth.detectors.unverified import (
    detect_mapping_stale,
    detect_test_failing,
    detect_unverified_no_mapping,
)

NODE_A = "tests/test_auto1.py::test_login"


class TestUnverifiedNoMapping:
    def test_one_aggregate_for_all_unmapped_tickets(self) -> None:
        t1 = ticket("AUTO-1", acceptance_criteria=[ac("AUTO-1#1"), ac("AUTO-1#2")])
        t2 = ticket("AUTO-2", acceptance_criteria=[ac("AUTO-2#1")])
        snapshot = trace([trace_link("AUTO-2#1", NODE_A)], collected=[NODE_A])
        found = detect_unverified_no_mapping(board([t1, t2], trace=snapshot), repo(), frozen_clock())

        assert len(found) == 1
        d = found[0]
        assert d.type is DiscrepancyType.UNVERIFIED_NO_MAPPING
        assert d.severity is DiscrepancySeverity.LOW
        assert d.subject == "AUTO:ac-mapping-coverage"
        assert d.proposed_action.verb is ActionVerb.NONE
        assert d.evidence, "a discrepancy without evidence is a claim without proof"
        # one evidence line per unmapped ticket, bound=no
        assert [e.ref for e in d.evidence] == ["AUTO-1"]
        assert d.evidence[0].detail["acs"] == "2"
        assert d.evidence[0].detail["bound"] == "no"

    def test_all_mapped_means_no_discrepancy(self) -> None:
        t1 = ticket("AUTO-1", acceptance_criteria=[ac("AUTO-1#1")])
        snapshot = trace([trace_link("AUTO-1#1", NODE_A)], collected=[NODE_A])
        assert detect_unverified_no_mapping(board([t1], trace=snapshot), repo(), frozen_clock()) == []

    def test_no_tickets_with_acs_means_no_discrepancy(self) -> None:
        t1 = ticket("AUTO-1")  # no acceptance criteria
        assert detect_unverified_no_mapping(board([t1]), repo(), frozen_clock()) == []

    def test_missing_trace_counts_every_ac_ticket_as_unmapped(self) -> None:
        t1 = ticket("AUTO-1", acceptance_criteria=[ac("AUTO-1#1")])
        found = detect_unverified_no_mapping(board([t1], trace=None), repo(), frozen_clock())
        assert len(found) == 1
        assert [e.ref for e in found[0].evidence] == ["AUTO-1"]

    def test_control_tickets_are_not_counted(self) -> None:
        t1 = ticket("AUTO-1", is_control=True, acceptance_criteria=[ac("AUTO-1#1")])
        assert detect_unverified_no_mapping(board([t1]), repo(), frozen_clock()) == []

    def test_every_unmapped_ticket_is_listed(self) -> None:
        t1 = ticket("AUTO-1", acceptance_criteria=[ac("AUTO-1#1")])
        t2 = ticket("AUTO-2", acceptance_criteria=[ac("AUTO-2#1")])
        found = detect_unverified_no_mapping(board([t1, t2]), repo(), frozen_clock())
        assert [e.ref for e in found[0].evidence] == ["AUTO-1", "AUTO-2"]


class TestMappingStale:
    def test_bound_test_no_longer_collected(self) -> None:
        t1 = ticket("AUTO-1", status="Done", acceptance_criteria=[ac("AUTO-1#1")])
        link = trace_link("AUTO-1#1", NODE_A)
        snapshot = trace([link], collected=["tests/other.py::test_gone"])
        found = detect_mapping_stale(board([t1], trace=snapshot), repo(), frozen_clock())

        assert len(found) == 1
        d = found[0]
        assert d.type is DiscrepancyType.UNVERIFIED_MAPPING_STALE
        assert d.severity is DiscrepancySeverity.MEDIUM
        assert d.subject == "AUTO-1#1"
        assert [e.kind for e in d.evidence] == [
            EvidenceKind.TEST_RESULT,
            EvidenceKind.JIRA_CHANGELOG,
        ]
        assert d.evidence[0].ref == NODE_A
        assert d.evidence[0].detail["collected"] == "no"
        assert d.evidence[1].ref == "AUTO-1"
        assert d.evidence[1].detail["binding"] == "AUTO-1#1"
        assert d.proposed_action.verb is ActionVerb.COMMENT
        assert d.proposed_action.target == "AUTO-1"

    def test_collected_binding_is_not_stale(self) -> None:
        t1 = ticket("AUTO-1", acceptance_criteria=[ac("AUTO-1#1")])
        snapshot = trace([trace_link("AUTO-1#1", NODE_A)], collected=[NODE_A])
        assert detect_mapping_stale(board([t1], trace=snapshot), repo(), frozen_clock()) == []

    def test_missing_trace_means_no_stale_mappings(self) -> None:
        t1 = ticket("AUTO-1", acceptance_criteria=[ac("AUTO-1#1")])
        assert detect_mapping_stale(board([t1], trace=None), repo(), frozen_clock()) == []

    def test_multiple_stale_bindings_sorted_by_ac_id(self) -> None:
        snapshot = trace(
            [
                trace_link("AUTO-2#1", "tests/test_b.py::test_b"),
                trace_link("AUTO-1#1", "tests/test_a.py::test_a"),
            ],
            collected=[],
        )
        found = detect_mapping_stale(board([], trace=snapshot), repo(), frozen_clock())
        assert [d.subject for d in found] == ["AUTO-1#1", "AUTO-2#1"]


class TestTestFailing:
    def test_failing_bound_test_on_done_ticket(self) -> None:
        t1 = ticket(
            "AUTO-1",
            status="Done",
            acceptance_criteria=[ac("AUTO-1#1"), ac("AUTO-1#2")],
        )
        node_b = "tests/test_auto1.py::test_logout"
        snapshot = trace(
            [trace_link("AUTO-1#1", NODE_A), trace_link("AUTO-1#2", node_b)],
            collected=[NODE_A, node_b],
            failing=[NODE_A],
        )
        found = detect_test_failing(board([t1], trace=snapshot), repo(), frozen_clock())

        assert len(found) == 1
        d = found[0]
        assert d.type is DiscrepancyType.UNVERIFIED_TEST_FAILING
        assert d.severity is DiscrepancySeverity.HIGH
        assert d.subject == "AUTO-1"
        # one TEST_RESULT proof per failing binding + the Jira status claim
        assert [e.kind for e in d.evidence] == [
            EvidenceKind.TEST_RESULT,
            EvidenceKind.JIRA_CHANGELOG,
        ]
        assert d.evidence[0].ref == NODE_A
        assert d.evidence[0].detail["outcome"] == "failed"
        assert d.evidence[1].detail["status"] == "Done"
        assert d.proposed_action.verb is ActionVerb.TRANSITION
        assert d.proposed_action.params["to"] == "In Progress"

    def test_multiple_failing_links_one_discrepancy_multiple_proofs(self) -> None:
        t1 = ticket("AUTO-1", status="Done", acceptance_criteria=[ac("AUTO-1#1")])
        node_b = "tests/test_auto1.py::test_logout"
        snapshot = trace(
            [trace_link("AUTO-1#1", NODE_A), trace_link("AUTO-1#2", node_b)],
            collected=[NODE_A, node_b],
            failing=[NODE_A, node_b],
        )
        found = detect_test_failing(board([t1], trace=snapshot), repo(), frozen_clock())
        assert len(found) == 1
        test_proofs = [e for e in found[0].evidence if e.kind is EvidenceKind.TEST_RESULT]
        assert len(test_proofs) == 2

    def test_passing_bound_test_on_done_ticket_is_clean(self) -> None:
        t1 = ticket("AUTO-1", status="Done", acceptance_criteria=[ac("AUTO-1#1")])
        snapshot = trace([trace_link("AUTO-1#1", NODE_A)], collected=[NODE_A], failing=[])
        assert detect_test_failing(board([t1], trace=snapshot), repo(), frozen_clock()) == []

    def test_failing_test_on_in_progress_ticket_is_not_flagged(self) -> None:
        # The ticket does not claim Done, so nothing is unverified yet.
        t1 = ticket("AUTO-1", status="In Progress", acceptance_criteria=[ac("AUTO-1#1")])
        snapshot = trace([trace_link("AUTO-1#1", NODE_A)], collected=[NODE_A], failing=[NODE_A])
        assert detect_test_failing(board([t1], trace=snapshot), repo(), frozen_clock()) == []

    def test_control_ticket_is_not_flagged(self) -> None:
        t1 = ticket("AUTO-1", status="Done", is_control=True, acceptance_criteria=[ac("AUTO-1#1")])
        snapshot = trace([trace_link("AUTO-1#1", NODE_A)], collected=[NODE_A], failing=[NODE_A])
        assert detect_test_failing(board([t1], trace=snapshot), repo(), frozen_clock()) == []

    def test_failing_binding_of_another_ticket_is_ignored(self) -> None:
        snapshot = trace([trace_link("AUTO-1#1", NODE_A)], collected=[NODE_A], failing=[NODE_A])
        t2 = ticket("AUTO-2", status="Done", acceptance_criteria=[ac("AUTO-2#1")])
        found = detect_test_failing(board([t2], trace=snapshot), repo(), frozen_clock())
        assert found == []
