"""The anti-gaming suite: gaming the board state must never pay.

Three moves straight from the Phase 3 plan, each asserted against the
frozen scoring policy:

1. Closing a ticket with no PR must not raise the score.
2. Adding an ``assert True`` test must not raise it — done_integrity
   counts only a CI check-run conclusion on the merge SHA, never a
   local pytest outcome.
3. Deleting a stale ticket must raise it less than fixing it — the
   deleted ticket returns as a ghost at full staleness penalty.

Plus the weight invariant from scoring_policy.yaml that makes (1)
hold: done_integrity >= progress_integrity + staleness_health, so
closing-without-proof can never beat doing the work.
"""

from __future__ import annotations

from factories import (
    ac,
    board,
    branch,
    check_run,
    commit,
    days_ago,
    frozen_clock,
    ghost,
    merged_pr,
    repo,
    ticket,
)

from groundtruth.scoring.dimensions import (
    done_integrity,
    duplication_health,
)
from groundtruth.scoring.policy import load_policy
from groundtruth.scoring.score import (
    compute_control_score,
    compute_score,
)

MERGE_SHA = "b" * 40


def _dim(score, name: str):
    return next(d for d in score.dimensions if d.name == name)


def _healthy_ip(key: str, br: str):
    return ticket(
        key,
        status="In Progress",
        branch=br,
        status_changed_at=days_ago(1),
        acceptance_criteria=[ac(f"{key}#1")],
    )


def _stale_ip(key: str, br: str, *, stale_days: int = 30):
    return ticket(
        key,
        status="In Progress",
        branch=br,
        status_changed_at=days_ago(stale_days),
        acceptance_criteria=[ac(f"{key}#1")],
    )


class TestCloseWithoutProof:
    def test_closing_a_stale_ticket_without_pr_never_raises_the_total(self) -> None:
        stale = _stale_ip("AUTO-1", "feature/AUTO-1", stale_days=20)
        healthy = _healthy_ip("AUTO-2", "feature/AUTO-2")
        honest = repo(
            [
                branch("feature/AUTO-1", [commit("a" * 40, 30)]),
                branch("feature/AUTO-2", [commit("c" * 40, 1)]),
            ]
        )
        closed = ticket(
            "AUTO-1",
            status="Done",
            branch="feature/AUTO-1",
            status_changed_at=days_ago(0),
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        # Same repo: no merged PR, no CI — the close is proof-less.
        before = compute_score(board([stale, healthy]), honest, frozen_clock())
        gamed = compute_score(board([closed, healthy]), honest, frozen_clock())

        assert gamed.total <= before.total
        # The close costs done_integrity: the ticket is in the denominator at 0.
        done = _dim(gamed, "done_integrity")
        assert done.value == 0.0
        assert done.numerator == 0
        assert done.denominator == 1
        assert any(
            e.detail.get("merged_pr") == "none" for e in done.evidence
        )

    def test_closing_a_healthy_ticket_without_pr_drops_the_total(self) -> None:
        first = _healthy_ip("AUTO-1", "feature/AUTO-1")
        second = _healthy_ip("AUTO-2", "feature/AUTO-2")
        healthy_repo = repo(
            [
                branch("feature/AUTO-1", [commit("a" * 40, 1)]),
                branch("feature/AUTO-2", [commit("c" * 40, 1)]),
            ]
        )
        closed = ticket(
            "AUTO-1",
            status="Done",
            branch="feature/AUTO-1",
            status_changed_at=days_ago(0),
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        before = compute_score(board([first, second]), healthy_repo, frozen_clock())
        gamed = compute_score(board([closed, second]), healthy_repo, frozen_clock())
        assert gamed.total <= before.total


class TestTrivialTestCannotRaiseScore:
    def test_green_check_on_the_branch_tip_is_not_ci_on_the_merge_sha(self) -> None:
        done = ticket(
            "AUTO-1",
            status="Done",
            branch="feature/AUTO-1",
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        head = commit("a" * 40, 2, subject="add trivial assert True test")
        pr = merged_pr(7, "feature/AUTO-1", merge_sha=MERGE_SHA)
        # A passing local run attaches to the branch tip, where the trivial
        # test lives — not to the commit that actually landed on main.
        r = repo(
            [branch("feature/AUTO-1", [head])],
            [pr],
            [check_run(head.sha)],
        )
        dim = done_integrity(board([done]), r, frozen_clock())
        assert dim.value == 0.0
        assert dim.numerator == 0
        assert dim.denominator == 1

    def test_failing_ci_on_the_merge_sha_fails(self) -> None:
        done = ticket(
            "AUTO-1",
            status="Done",
            branch="feature/AUTO-1",
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        pr = merged_pr(7, "feature/AUTO-1", merge_sha=MERGE_SHA)
        r = repo(
            [branch("feature/AUTO-1", [commit("a" * 40, 2)])],
            [pr],
            [check_run(MERGE_SHA, conclusion="failure")],
        )
        dim = done_integrity(board([done]), r, frozen_clock())
        assert dim.value == 0.0

    def test_green_ci_on_the_merge_sha_is_the_only_pass_path(self) -> None:
        done = ticket(
            "AUTO-1",
            status="Done",
            branch="feature/AUTO-1",
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        pr = merged_pr(7, "feature/AUTO-1", merge_sha=MERGE_SHA)
        r = repo(
            [branch("feature/AUTO-1", [commit("a" * 40, 2)])],
            [pr],
            [check_run(MERGE_SHA)],
        )
        dim = done_integrity(board([done]), r, frozen_clock())
        assert dim.value == 1.0
        assert dim.numerator == 1

    def test_trivial_local_test_does_not_move_the_total(self) -> None:
        done = ticket(
            "AUTO-1",
            status="Done",
            branch="feature/AUTO-1",
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        head = commit("a" * 40, 2, subject="add trivial assert True test")
        pr = merged_pr(7, "feature/AUTO-1", merge_sha=MERGE_SHA)
        without_local_run = repo(
            [branch("feature/AUTO-1", [head])], [pr], [check_run(MERGE_SHA)]
        )
        with_local_run = repo(
            [branch("feature/AUTO-1", [head])],
            [pr],
            [check_run(MERGE_SHA), check_run(head.sha)],
        )
        before = compute_score(board([done]), without_local_run, frozen_clock())
        after = compute_score(board([done]), with_local_run, frozen_clock())
        assert after.total <= before.total


class TestDeleteVsFix:
    def test_deleting_a_stale_ticket_raises_less_than_fixing_it(self) -> None:
        policy = load_policy()
        stale = _stale_ip("AUTO-1", "feature/AUTO-1", stale_days=20)
        healthy = _healthy_ip("AUTO-2", "feature/AUTO-2")
        quiet = repo(
            [
                branch("feature/AUTO-1", [commit("a" * 40, 30)]),
                branch("feature/AUTO-2", [commit("c" * 40, 1)]),
            ]
        )
        fixed_repo = repo(
            [
                branch("feature/AUTO-1", [commit("d" * 40, 1)]),
                branch("feature/AUTO-2", [commit("c" * 40, 1)]),
            ]
        )
        fixed_ticket = ticket(
            "AUTO-1",
            status="In Progress",
            branch="feature/AUTO-1",
            status_changed_at=days_ago(1),
            acceptance_criteria=[ac("AUTO-1#1")],
        )

        baseline = compute_score(board([stale, healthy]), quiet, frozen_clock())
        deleted = compute_score(
            board([healthy], ghosts=[ghost("AUTO-1", status="In Progress")]),
            quiet,
            frozen_clock(),
        )
        fixed = compute_score(board([fixed_ticket, healthy]), fixed_repo, frozen_clock())

        # Deleting cannot even match doing nothing: the ghost re-enters both
        # the staleness budget and progress_integrity at full penalty.
        assert deleted.total <= baseline.total
        assert deleted.total < fixed.total
        progress = _dim(deleted, "progress_integrity")
        assert progress.denominator == 2  # healthy ticket + the ghost
        assert progress.numerator == 1
        staleness = _dim(deleted, "staleness_health")
        assert staleness.denominator == 2 * policy.stale_day_cap
        assert staleness.numerator == policy.stale_day_cap - 1  # only AUTO-2

    def test_fixing_a_stale_ticket_raises_the_total(self) -> None:
        stale = _stale_ip("AUTO-1", "feature/AUTO-1", stale_days=20)
        healthy = _healthy_ip("AUTO-2", "feature/AUTO-2")
        quiet = repo(
            [
                branch("feature/AUTO-1", [commit("a" * 40, 30)]),
                branch("feature/AUTO-2", [commit("c" * 40, 1)]),
            ]
        )
        fixed_repo = repo(
            [
                branch("feature/AUTO-1", [commit("d" * 40, 1)]),
                branch("feature/AUTO-2", [commit("c" * 40, 1)]),
            ]
        )
        fixed_ticket = ticket(
            "AUTO-1",
            status="In Progress",
            branch="feature/AUTO-1",
            status_changed_at=days_ago(1),
            acceptance_criteria=[ac("AUTO-1#1")],
        )
        baseline = compute_score(board([stale, healthy]), quiet, frozen_clock())
        fixed = compute_score(board([fixed_ticket, healthy]), fixed_repo, frozen_clock())
        assert fixed.total > baseline.total


class TestWeightInvariant:
    def test_done_weight_covers_progress_plus_staleness(self) -> None:
        # The frozen-policy inequality that makes closing-without-proof
        # never beat doing the work (see scoring_policy.yaml).
        policy = load_policy()
        lost_by_closing = policy.weight("done_integrity")
        lost_by_staying = round(
            policy.weight("progress_integrity") + policy.weight("staleness_health"), 6
        )
        assert lost_by_closing >= lost_by_staying


class TestDuplicateConfirmation:
    def test_model_suspicion_alone_cannot_move_duplication_health(self) -> None:
        # Suspected pairs move nothing until a human confirms in the ledger.
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout")
        t2 = ticket("AUTO-2", summary="Fix login timeouts in checkout")
        suspected_only = duplication_health(
            board([t1, t2]), repo(), frozen_clock(), ledger_entries=[]
        )
        assert suspected_only.value == 1.0
        assert suspected_only.numerator == 2

    def test_confirmed_pair_drops_duplication_health(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout")
        t2 = ticket("AUTO-2", summary="Fix login timeouts in checkout")
        confirmed = [
            {
                "action": "duplicate.confirm",
                "outcome": "ok",
                "approval": "human-review-1",
                "subject": "AUTO-1+AUTO-2",
            }
        ]
        dim = duplication_health(
            board([t1, t2]), repo(), frozen_clock(), ledger_entries=confirmed
        )
        assert dim.value == 0.5
        assert dim.numerator == 1
        assert dim.denominator == 2

    def test_confirmation_without_human_approval_does_not_count(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout")
        t2 = ticket("AUTO-2", summary="Fix login timeouts in checkout")
        # A machine-written entry with no approval ref is not a confirmation.
        unapproved = [
            {
                "action": "duplicate.confirm",
                "outcome": "ok",
                "approval": None,
                "subject": "AUTO-1+AUTO-2",
            }
        ]
        dim = duplication_health(
            board([t1, t2]), repo(), frozen_clock(), ledger_entries=unapproved
        )
        assert dim.value == 1.0

    def test_refused_confirmation_does_not_count(self) -> None:
        t1 = ticket("AUTO-1", summary="Fix login timeout on checkout")
        t2 = ticket("AUTO-2", summary="Fix login timeouts in checkout")
        refused = [
            {
                "action": "duplicate.confirm",
                "outcome": "refused",
                "approval": "human-review-1",
                "subject": "AUTO-1+AUTO-2",
            }
        ]
        dim = duplication_health(
            board([t1, t2]), repo(), frozen_clock(), ledger_entries=refused
        )
        assert dim.value == 1.0


class TestControlGroup:
    def test_control_tickets_never_enter_the_main_score(self) -> None:
        broken = ticket("AUTO-1", status="To Do")  # no ACs -> ac_validity fail
        pristine_control = ticket(
            "CTRL-1",
            status="To Do",
            is_control=True,
            acceptance_criteria=[ac("CTRL-1#1")],
        )
        score = compute_score(board([broken, pristine_control]), repo(), frozen_clock())

        main_ac = _dim(score, "ac_validity")
        assert main_ac.denominator == 1
        assert main_ac.numerator == 0

        control = compute_control_score(board([broken, pristine_control]), repo(), frozen_clock())
        assert control is not None
        control_ac = _dim(control, "ac_validity")
        assert control_ac.denominator == 1
        assert control_ac.numerator == 1
        assert score.control_group is not None

    def test_no_control_tickets_means_no_control_group(self) -> None:
        only_main = ticket("AUTO-1", status="To Do", acceptance_criteria=[ac("AUTO-1#1")])
        score = compute_score(board([only_main]), repo(), frozen_clock())
        assert score.control_group is None
        assert compute_control_score(board([only_main]), repo(), frozen_clock()) is None
