from groundtruth.detectors.duplicate import detect_duplicate
from groundtruth.detectors.merged_open import detect_merged_pr_ticket_open
from groundtruth.detectors.orphan_branch import detect_orphan_branch
from groundtruth.detectors.stale import detect_stale
from groundtruth.detectors.unverified import (
    detect_mapping_stale,
    detect_test_failing,
    detect_unverified_no_mapping,
)

__all__ = [
    "detect_duplicate",
    "detect_mapping_stale",
    "detect_merged_pr_ticket_open",
    "detect_orphan_branch",
    "detect_stale",
    "detect_test_failing",
    "detect_unverified_no_mapping",
]
