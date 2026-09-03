# Board Truthfulness Score - evidence log

- run: 1393ef76-c4c2-415b-bac1-7a7cf206e758
- policy: 2026-09-01.1 (sha256 274c3d109dd80a0fdca907d1fc79f55b71f0f7aa98bc1ecdfae01ca2a52d3193)
- as_of: 2026-09-01T12:00:00+00:00
- board snapshot: b10d9ad4b820d799b9fa8a9d85e710e0a11efe5721ac1759e9c7e1912d56772b
- total: 0.6725
- control group: 0.9846

# Main board

## ac_validity - 2/3 (value 0.6667, weight 0.15, contributes 0.1000)
- [pass] jira_changelog AUTO-1 https://groundtruth-demo.atlassian.net/browse/AUTO-1
    ac_total=1; ac_wellformed=1; summary=Fix login flakiness; verdict=pass
- [pass] jira_changelog AUTO-2 https://groundtruth-demo.atlassian.net/browse/AUTO-2
    ac_total=1; ac_wellformed=1; summary=Support CSV export; verdict=pass
- [fail] jira_changelog AUTO-4 https://groundtruth-demo.atlassian.net/browse/AUTO-4
    ac_total=0; ac_wellformed=0; summary=Remove legacy cache; verdict=fail

## progress_integrity - 0/1 (value 0.0000, weight 0.20, contributes 0.0000)
- [fail] commit aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa https://github.com/yasiru-101/Groundtruth/commit/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    age_days=20; author_date=2026-08-12T10:00:00+00:00; linked_branch=feature/AUTO-1; status=In Progress; status_changed_at=2026-08-05 10:00:00+00:00; verdict=fail; window_days=7

## done_integrity - 1/1 (value 1.0000, weight 0.35, contributes 0.3500)
- [pass] pr 2 https://github.com/yasiru-101/Groundtruth/pull/2
    head_ref=feature/AUTO-2; merge_sha=merge-auto-2; merged_at=2026-08-18 09:00:00+00:00; ticket=AUTO-2; verdict=pass
- [pass] check_run merge-auto-2 https://github.com/yasiru-101/Groundtruth/commit/merge-auto-2
    check=CI; conclusion=success; verdict=pass

## staleness_health - 29/60 ticket-days (value 0.4833, weight 0.15, contributes 0.0725)
- [fail] jira_changelog AUTO-1 https://groundtruth-demo.atlassian.net/browse/AUTO-1
    stale_day_cap=30; stale_days=27; status=In Progress; status_changed_at=2026-08-05 10:00:00+00:00; verdict=fail
- [pass] jira_changelog AUTO-4 https://groundtruth-demo.atlassian.net/browse/AUTO-4
    stale_day_cap=30; stale_days=4; status=To Do; status_changed_at=2026-08-28 09:00:00+00:00; verdict=pass

## duplication_health - 2/2 tickets (value 1.0000, weight 0.15, contributes 0.1500)
- [pass] ledger confirmed-duplicates ledger
    active_tickets=2; confirmed_pairs=0; note=no human-confirmed duplicates in the ledger; verdict=pass

# Control group (never touched by Delivery)

total: 0.9846

## ac_validity - 1/1 (value 1.0000, weight 0.15, contributes 0.1500)
- [pass] jira_changelog AUTO-3 https://groundtruth-demo.atlassian.net/browse/AUTO-3
    ac_total=1; ac_wellformed=1; summary=Dark mode toggle; verdict=pass

## progress_integrity - 1/1 (value 1.0000, weight 0.20, contributes 0.2000)
- [pass] commit cccccccccccccccccccccccccccccccccccccccc https://github.com/yasiru-101/Groundtruth/commit/cccccccccccccccccccccccccccccccccccccccc
    author_date=2026-08-31T10:00:00+00:00; branch=feature/AUTO-3; ticket=AUTO-3; verdict=pass

## done_integrity - EXCLUDED (no Done tickets)

## staleness_health - 28/30 ticket-days (value 0.9333, weight 0.15, contributes 0.1400)
- [pass] jira_changelog AUTO-3 https://groundtruth-demo.atlassian.net/browse/AUTO-3
    stale_day_cap=30; stale_days=2; status=In Progress; status_changed_at=2026-08-30 09:00:00+00:00; verdict=pass

## duplication_health - 1/1 tickets (value 1.0000, weight 0.15, contributes 0.1500)
- [pass] ledger confirmed-duplicates ledger
    active_tickets=1; confirmed_pairs=0; note=no human-confirmed duplicates in the ledger; verdict=pass
