# Groundtruth — Implementation Plan

**What we're building.** A multi-agent system that reconciles a Jira board against Git reality and can prove every claim it makes. Four agents plus a stretch planner over a governance layer: an **Intake Analyst** (raw notes → ready tickets), a **Board Steward** (deterministic Jira × Git diff → evidence-bearing discrepancies), a **Delivery Agent** (ticket → tests-first → code → PR with a real traceability matrix), and a **Reporting Agent**. Headline output is a **Board Truthfulness Score** where every point cites an artifact the system did not produce.

**Root:** `D:\MIT\Agentic Jira` · **Python 3.13** · Real Jira Cloud + GitHub via `gh` · LLM at exactly three hops (intake decomposition, code generation/repair, report prose); everything else deterministic.

**Five phases. Each ends with a runnable command and passing tests. Together they complete the application** — nothing is deferred to a stretch backlog.

**Ordering rationale:** the Board Steward is the differentiator and the Delivery Agent is the fragile part, so Steward ships first (Phase 3) and Delivery last (Phase 5). If Phase 5 runs long, Phases 1–4 are still a complete, demonstrable product.

---

## CLI surface (final state)

| Command | Phase | Behaviour |
| --- | --- | --- |
| `groundtruth seed` / `reset` | 2 | Build / tear down the synthetic messy board + repo history |
| `groundtruth audit` | 3 | Emit discrepancies with evidence |
| `groundtruth score` | 3 | Compute Board Truthfulness Score + evidence log |
| `groundtruth intake <file>` | 4 | Raw text → tickets (propose, then apply) |
| `groundtruth plan` | 4 | Capacity-checked sprint proposal |
| `groundtruth deliver <KEY>` | 5 | Branch → red → green → PR |
| `groundtruth report` | 5 | Standup digest, sprint health, score delta |
| `--mode {dry-run,propose,apply}` | 1 | Global. `dry-run` is default; `apply` requires a changeset hash |
| `--run-mode {live,record,replay}` | 2 | Global. Adapter I/O mode |

---

# Phase 1 — Foundation, contracts, safety core

**Goal:** make destructive git operations structurally impossible and every action auditable, before any agent exists.

### Files

```
pyproject.toml            .gitignore (written BEFORE any git init)
.env.example              README.md
src/groundtruth/
  __main__.py             # CLI skeleton, all subcommands registered, bodies stubbed
  config.py               # Settings, RunMode, ExecMode; fail-fast env validation
  clock.py                # Clock protocol; SystemClock, FrozenClock
  ids.py                  # idempotency keys, branch slugs
  contracts/
    story.py discrepancy.py ledger.py score.py trace.py testrun.py
  ledger/
    writer.py             # append-only JSONL, hash-chained, fsync
    reader.py             # replay, state projection, chain verification
  safety/
    workspace.py          # WorkspaceGuard
    git_guard.py          # the ONLY module allowed to invoke git
    approval.py           # ChangeSet, propose → apply bound to hash
    redact.py             # secret scrubbing
workspace/.groundtruth-sandbox     # sentinel
artifacts/.gitkeep
tests/
  test_safety_guard.py test_ledger_chain.py test_redact.py test_contracts.py
```

**Dependencies (pinned):** `pydantic>=2.6`, `httpx>=0.27`, `pyyaml>=6`, `pytest>=8`, `pytest-json-report>=1.5`, `python-dotenv>=1.0`. None are currently installed — including `pytest`.

### Data contracts

Pydantic v2, `extra="forbid"`, frozen where practical.

**`Evidence`** — discriminated union, every variant externally checkable.
`kind: "commit"|"pr"|"check_run"|"jira_changelog"|"test_result"|"branch"` · `ref` (SHA / PR# / node id) · `url` (clickable) · `observed_at` · `detail: dict[str,str]`

**`Discrepancy`** — `discrepancy_id` = sha256(type + subject + sorted evidence refs), so it dedupes across runs · `type` · `severity` · `subject` · **`evidence: list[Evidence]` with a non-empty validator** · `proposed_action` · `detected_at` · `as_of` · `detector_version`

> The non-empty evidence validator is the whole thesis in one line: a discrepancy that cannot cite evidence cannot be constructed.

**`ProposedAction`** — `verb: TRANSITION|COMMENT|LINK|CREATE_TICKET|CLOSE_DUPLICATE|NONE` · `target` · `params` · `reversible` · `requires_approval: bool = True` (never defaulted False)

**`Story`** — `idempotency_key` = sha256(source_doc_id + normalized AC text) · `jira_key: str|None` · `summary` · `description` · `acceptance_criteria: list[AcceptanceCriterion]` · `points` · `components` · `depends_on` · `status` · `dor: DefinitionOfReadyResult` · `source: ProvenanceRef` (doc id + char span + llm_call_id) · `dedupe: DedupeVerdict|None`

> Never key idempotency on summary text — a model rephrasing a summary silently double-creates the ticket.

**`AcceptanceCriterion`** — `ac_id` = `"{story_key}-AC{n}"`, stable across rewording · `given`/`when`/`then` · `raw` · `is_wellformed`

**`DefinitionOfReadyResult`** — `passed` · `failures: list[str]` (machine codes: `NO_AC`, `AC_MALFORMED`, `NO_POINTS`, `NO_COMPONENT`, `CIRCULAR_DEP`) · `checked_at`

**`DedupeVerdict`** — `candidate_jira_keys` · `similarity` · `method` · `threshold` · `human_confirmed: bool|None`

**`LedgerEntry`** — `seq` · `run_id` · `entry_id` · `ts` (UTC ISO-8601) · `actor` · `action` · `mode` · `subject` · `inputs_hash` · `outputs_hash` · `evidence` · `approval: ApprovalRef|None` (required when mode=`APPLY` and the action writes) · `outcome: ok|refused|error` · `error` · **`prev_hash` / `this_hash`**

**`TraceLink`** — `ac_id` · `test_node_id` · `bound_by: "manifest"` · `bound_at` · `test_file_hash`
**`TraceMatrixRow`** — `ac_id` · `ac_text` · `test_node_ids` · `status: passed|failed|missing|error|skipped|not_collected` · `red_proof` · `evidence`
**`RedProof`** — `node_id` · `failed_at` · `failure_kind: assertion|import_error|collection_error` · `longrepr_excerpt`
**`TestRunResult`** — `run_id` · `exit_code` · `tests: dict[node_id, TestOutcome]` · `collected_node_ids` · `raw_report_path`
**`DimensionScore`** — `name` · `value: float|None` · `numerator` · `denominator` · `weight` · `evidence` · `excluded_reason`
**`TruthfulnessScore`** — `total` · `dimensions` · `policy_version` · `policy_hash` · `as_of` · `board_snapshot_hash` · `control_group` · `evidence_log_path`

### Safety envelope

The hazard is concrete: a `git add .` inside a repo rooted at a home directory stages private keys and cloud credentials, and a `gh` token with `repo` scope publishes them on push. The Windows home directory on this machine *is* an uncommitted repo with no `.gitignore`.

1. **No ambient repo.** Every git write takes an explicit sandbox path. No code path inherits `cwd`.
2. **`WorkspaceGuard`, re-checked on every git write call** — not once at startup: resolve realpath; `git rev-parse --show-toplevel` must equal the sandbox root *exactly*; root must resolve under `allowed_root = D:/MIT/Agentic Jira`; root must contain the `.groundtruth-sandbox` sentinel carrying the run's workspace id; root must never be the user's home directory, a parent of it, or an ancestor of home; remote must match the expected demo repo or be explicitly local-only. **Fail closed** — any check erroring is a refusal.
3. **Single choke point.** `safety/git_guard.py` is the only module permitted to invoke git, enforced by a test that greps the tree for git subprocess calls outside it and fails.
4. **Allowlist + banned argument forms.** Allow `init, checkout -b, add <explicit-paths>, commit -m, push, rev-parse, log, status, diff, branch, show`. **Hard-ban** `add .`, `add -A`, `add -u`, `commit -a`, `clean`, `reset --hard`, `checkout .`, `push --force`, and any pathspec that is `.`, absolute, or contains `..`. `shell=True` rejected outright.
5. **`GIT_DIR`/`GIT_WORK_TREE` pinned** in the subprocess env on every write, so git cannot walk up and discover an enclosing repo even if cwd is wrong.
6. **Blocking preflight** detects a repo rooted at home and prints remediation. It never remediates automatically — that is user data.
7. **Secrets.** Credentials only from env / gitignored `.env`; `.env.example` holds names only. Fail fast listing missing *names*, never values. `redact.py` scrubs `gho_`, `ghp_`, `ATATT`, JWT-shaped and `Bearer` patterns on every ledger write, report render, and LLM prompt.
8. **Approval.** `propose` writes a `ChangeSet` to `artifacts/`; `apply` requires that changeset's hash as an argument, so approval binds to exact reviewed content.

### Tests
Every banned git form invoked from the home directory → refused, each with a `refused` ledger entry. Sandbox guard exercised through the **real spaced path**, not a clean temp dir. Hash chain verification passes, then fails after tampering with one line. `Discrepancy` without evidence raises. Redactor round-trip.

### Exit criteria
```
groundtruth --help                 # all subcommands listed
pytest tests/ -v                   # green
python -m groundtruth._demo_unsafe # attempts `git add .` from home → REFUSED + ledger entry
```
Assert the home repo's index is byte-identical before and after the whole suite.

---

# Phase 2 — Adapters, record/replay, seeder

**Goal:** every external system reachable behind a replayable envelope, and a reproducible messy board to reconcile.

### Files

```
src/groundtruth/adapters/
  base.py            # request hashing, LIVE/RECORD/REPLAY envelope, fixture store
  jira.py            # REST v3: search, get, create, transitions, comments, changelog
  github.py          # gh CLI wrapper: pr list/view/create, check-runs
  gitlog.py          # read-only: branches, commits, author dates, merge SHAs
  pytest_runner.py   # subprocess pytest --json-report → TestRunResult
  llm.py             # exactly 3 named prompts, cached by input hash
src/groundtruth/seed/
  scenario.yaml seed_jira.py seed_git.py reset.py
tests/
  test_adapters_replay.py test_jira_pagination.py test_seed_idempotent.py
fixtures/            # captured payloads, keyed by request hash
```

### Implementation notes

- **Jira search migrated.** `GET`/`POST /rest/api/3/search` are deprecated → **`/rest/api/3/search/jql`**, and `fields` must now be passed explicitly (e.g. `fields=*all`). The new endpoint also **drops `total`**, so score denominators require paginating to completion via `nextPageToken`. Confirm whether an approximate-count endpoint is available; if not, full pagination is mandatory. Issue creation, transitions, and comments are unaffected.
- **Transitions are workflow-specific.** Resolve transition ids from the transitions endpoint and fail with the available list rather than a bare error, since a target status name may not exist on a given board's workflow.
- **`gh` via arg-lists, `shell=False`.** All `gh` writes (`pr create`, `repo create`) route through `git_guard` with an allowlisted target repo slug; a push to an unexpected slug is refused.
- **Record/replay.** Fixtures keyed by sha256 of (method, url, sorted params, body). `REPLAY` raises on a cache miss rather than falling through to the network — a silent live call during a demo defeats the point.
- **Seeder** builds from `scenario.yaml`: tickets stale by N days, a merged PR whose ticket is open, an orphan branch with real commits, a Done ticket with no test binding, a near-duplicate pair. It **refuses to run against any Jira project key other than the configured demo key.** Plants defects the detectors are not tuned on, and marks a control group the Delivery Agent will never touch.
- **Clock injection.** Wall-clock `now()` makes scores non-reproducible between rehearsal and stage, and rots fixtures. `REPLAY` pins `as_of` to the recorded run timestamp.

### Exit criteria
```
groundtruth seed --run-mode live      # board + repo history created
groundtruth seed --run-mode live      # rerun → zero duplicates
groundtruth reset
pytest tests/ -v
```
Then capture a `LIVE` read pass into `fixtures/` and confirm the same reads succeed in `REPLAY` **with the network disabled**.

---

# Phase 3 — Board Steward + Truthfulness Score

**Goal:** the differentiator. `audit` and `score` fully working, zero LLM calls in this path.

### Files

```
src/groundtruth/detectors/
  stale.py merged_open.py orphan_branch.py unverified.py duplicate.py
src/groundtruth/agents/steward.py
src/groundtruth/trace/manifest.py        # read + validate (write lands in Phase 5)
src/groundtruth/scoring/
  dimensions.py score.py evidence_log.py
scoring_policy.yaml                      # weights + policy_version — FROZEN HERE
tests/
  test_detectors_stale.py test_detectors_merged_open.py
  test_detectors_orphan.py test_detectors_unverified.py test_detectors_duplicate.py
  test_score_antigaming.py test_score_nulls.py
```

Each detector is a pure function `(BoardState, RepoState, Clock) -> list[Discrepancy]`, one file per rule, golden-fixture tested.

| Type | Rule |
| --- | --- |
| `STALE_IN_PROGRESS` | In Progress, no commit on a linked branch within the staleness window |
| `MERGED_PR_TICKET_OPEN` | PR merged, ticket not Done |
| `ORPHAN_BRANCH` | Branch with commits, no corresponding ticket |
| `UNVERIFIED_NO_MAPPING` | No manifest entry for the ticket's ACs |
| `UNVERIFIED_MAPPING_STALE` | Manifest entry exists, node id no longer collected |
| `UNVERIFIED_TEST_FAILING` | Bound test failing while the ticket claims Done |
| `DUPLICATE_SUSPECTED` | Deterministic similarity (token-set), proposal only, never auto-resolved |

> **Why `UNVERIFIED` splits three ways.** Seeded legacy tickets have no binding because no Delivery Agent ever ran on them, so one detector would flag 100% of them — grading the seeder, not the board. `NO_MAPPING` is reported as *coverage-of-mapping*, a baseline; only `MAPPING_STALE` and `TEST_FAILING` are per-ticket defects.

### Score

Five dimensions, each in [0,1], each rendered as **numerator/denominator, never a bare float**.

| Dimension | Definition | External witness |
| --- | --- | --- |
| `ac_validity` | tickets whose ACs parse as well-formed G-W-T and pass DoR | deterministic parser |
| `progress_integrity` | of In Progress: ≥1 commit in-window on a branch linked to the key | commit SHA + author date |
| `done_integrity` | of Done: merged PR **and** passing CI check-run on the merge SHA | PR # + check-run conclusion |
| `staleness_health` | 1 − (weighted stale-days / cap) over active tickets | Jira changelog timestamps |
| `duplication_health` | 1 − (human-confirmed duplicate pairs / active tickets) | ledger approval entry |

Four rules that keep it from being circular:

1. **`done_integrity` cites the GitHub Actions check-run conclusion** for the merged SHA via `gh api` — never our own local pytest run. Local pytest is evidence for a **PR body**; CI conclusion is evidence for the **score**. Never conflate them.
2. **`scoring_policy.yaml` is frozen in this phase**, before Phase 4/5 agents exist that could be tuned against it. `policy_version` + `policy_hash` recorded in every score record.
3. **Anti-gaming suite is shipped, not aspirational.** Closing a ticket with no PR must not raise the score; adding `assert True` must not raise it; deleting a stale ticket must raise it *less* than fixing it.
4. **Control group.** Report a second score over tickets Delivery never touches.

Unmeasurable dimensions score `null` and are **excluded from the denominator with the exclusion printed.** Silently scoring a missing dimension as 1.0 is the most common way a metric like this lies.

### Exit criteria
```
groundtruth audit --run-mode replay    # discrepancies, each with clickable evidence
groundtruth score --run-mode replay    # baseline score + itemised evidence log
pytest tests/ -v
```
Assert every emitted discrepancy has non-empty evidence and that `null` dimensions are visibly excluded.

---

# Phase 4 — Intake Analyst + Sprint Planner + live writes

**Goal:** the board-authoring half. First LLM hop, and the first code permitted to mutate real Jira.

### Files

```
src/groundtruth/agents/intake.py     # LLM hop (a)
src/groundtruth/agents/planner.py    # deterministic, no LLM
src/groundtruth/prompts/decompose.md
tests/
  test_intake_idempotency.py test_dor_gate.py test_dedupe.py test_planner.py
```

### Intake

Raw prose → `Story[]` with Given-When-Then ACs, points, components, `depends_on`. Then, deterministically:

- **DoR gate** refuses malformed stories with machine codes. A refusal is a first-class successful outcome, logged, not an exception.
- **Idempotency** via `ids.py`: the key is written to a Jira label and mirrored in local state. A rerun — including one where the model rephrases the summary — creates zero new tickets.
- **Dedupe** emits `DUPLICATE_SUSPECTED` candidates with a recorded similarity, method, and threshold. **Never auto-resolves**, and duplicates only affect the score after `human_confirmed` is recorded in the ledger, so a model's judgment cannot move the headline number.
- **Provenance**: every story records source doc id, character span, and `llm_call_id`.

### Planner

Fully deterministic: velocity from closed-ticket history, dependency topological sort with cycle detection, load balancing across assignees, over-commitment flagged against capacity. Emits a sprint **proposal**.

### Live writes
This is where `propose → apply` gets exercised for real. `propose` writes a `ChangeSet`; `apply` requires its hash; every applied action lands in the ledger with an `ApprovalRef`.

### Exit criteria
```
groundtruth intake notes.md --mode propose
groundtruth intake notes.md --mode apply --changeset <hash>   # tickets created in Jira
groundtruth intake notes.md --mode apply --changeset <hash>   # rerun → 0 new tickets
groundtruth plan
pytest tests/ -v
```
Verify by hand in the Jira UI that ticket count is N and not 2N, and that one malformed item was refused with reasons.

---

# Phase 5 — Delivery Agent + Reporting + end-to-end

**Goal:** close the loop. Ticket → tests-first → code → PR with a matrix that is generated rather than asserted.

### Files

```
src/groundtruth/delivery/
  test_author.py     # AC → pytest file + manifest entries
  red_gate.py        # proves failure is assertion-based
  test_lock.py       # tests immutable during repair
  repair.py          # bounded loop, src/ only
  pr_body.py         # matrix rendered from a real TestRunResult
src/groundtruth/trace/reconcile.py
src/groundtruth/agents/delivery.py
src/groundtruth/agents/reporting.py     # LLM hop (c)
src/groundtruth/prompts/implement.md repair.md report.md
tests/
  test_red_gate.py test_test_lock.py test_trace_validation.py
  test_pr_body.py test_e2e.py
```

### Traceability: manifest as sole authority

A generated `trace_manifest.json` is authoritative; a `@pytest.mark.ac(...)` marker is emitted alongside for readability only.

Rejected alternatives: naming conventions (brittle, break on parametrize, encode no AC text); docstring parsing (drifts silently with no failure signal); markers alone (live inside the very files the repair loop may touch).

1. `test_author.py` writes the test file **and** `TraceLink` entries carrying `ac_id`, `test_node_id`, `test_file_hash`.
2. **Validation is mandatory:** run `pytest --collect-only -q --json-report`; every manifest node id must appear in `collected_node_ids`. A manifest entry pointing at a nonexistent node is a **hard error**, never a silent skip. *This is what makes the matrix real — the binding is proven against pytest's collector, not asserted by its generator.*
3. `reconcile.py` joins manifest × `TestRunResult`. **An AC with no link renders `missing`, not omitted** — the PR body must show its own gaps. Every checkbox is a function of a node id's outcome in a stored pytest JSON artifact.
4. The manifest is committed, so claimed bindings appear in the PR diff.

### Red gate
A test importing a nonexistent module trivially "fails first" while testing nothing. `red_gate` requires `outcome == failed` with a **non-collection** failure, or records the weaker `RED_VIA_IMPORT_ERROR` class, which must convert to a real assertion failure once the module skeleton exists.

### Repair integrity — six structural layers

The classic failure of self-healing agents is deleting the failing assertion to force green. Principle: **do not ask the model not to edit tests; make test edits mechanically impossible to commit.**

1. **Hash lock.** sha256 of every test file + the manifest recorded before repair, re-hashed after *every* iteration. Mismatch → revert from the locked copy, abort the iteration, write a `refused` entry (`TEST_MUTATION_ATTEMPT`). Not a warning.
2. **Write-path partition.** Repair is granted `src/` only. `tests/` and the manifest are owned by `test_author.py`, which does not run during repair. Enforced in the file-writing primitive, not the prompt.
3. **Read-only posture.** Test files set `stat.S_IREAD` for the repair window.
4. **Collection monotonicity.** `len(collected_node_ids)` never decreases and every AC-bound node stays collected — catches deletion, rename, and injected `@pytest.mark.skip`.
5. **Skip/xfail ban.** Post-repair scan for newly added `skip`, `xfail`, `pytest.raises` wrapping the asserted call, or `assert True` in bound tests.
6. **Assertion-density floor.** Assertion count per bound test recorded via `ast` at lock time; must not decrease. Blocks assertion *weakening*, which hashing catches but semantic review may not.

Bounded at 3 iterations, per-iteration diff written to the ledger. **If the loop exits without green, the PR opens as a draft with the failing matrix shown honestly.** Never fabricate green.

### Reporting
LLM hop (c) writes prose over numbers already computed deterministically: standup digest, sprint health, score delta with control-group figure.

### Exit criteria
```
groundtruth deliver AUTO-14 --mode apply --changeset <hash>
groundtruth report
groundtruth score            # compare against Phase 3 baseline
pytest tests/ -v
```

**End-to-end acceptance — the real gate:**

1. `seed → audit → intake → plan → deliver → report → score` in `REPLAY`, then once in `LIVE`.
2. In `LIVE`, verify **by hand**: open the Jira ticket; open the PR; click a cited SHA; confirm the CI check-run conclusion matches what the score claims.
3. Adversarial suite: delete an assertion, add `@pytest.mark.skip`, replace a test body with `assert True`, edit the manifest — each **refused**, files byte-identical afterwards.
4. `DRY_RUN` is the default for every command and produces **zero** writes.
5. Re-verify the hash chain over the full run ledger.
6. Full run in `REPLAY` with the **network physically disabled**.

---

## Cut order if time runs short

Strictly in this order: Sprint Planner → risk register → `DUPLICATE_SUSPECTED` → repair iterations 3→1 → live mode (keep replay) → Delivery multi-ticket → single scripted ticket.

**Never cut:** Phase 1 safety · hash-chained ledger · the non-empty evidence validator · the anti-gaming suite · generated-not-asserted matrix.

---

## Environment gotchas (verified on this machine)

- **`pytest`, `pydantic`, and a JSON reporter are not installed.** The entire traceability mechanism depends on machine-readable pytest output — pin `pytest` + `pytest-json-report` in Phase 1 (fallback `--junit-xml`).
- **Space in the project path.** `D:\MIT\Agentic Jira` contains a space. Never interpolate the path into a command string; pass `GIT_DIR`/`GIT_WORK_TREE` as env values. Phase 1 must exercise the git guard through the **real spaced path** — a temp-dir test without a space hides the bug until stage.
- **Cross-volume.** Project on `D:`, home on `C:`. `os.path.relpath` raises `ValueError` across Windows drives, so use `Path.is_relative_to` for all path containment checks.
- **Windows I/O.** JSONL written with `newline="\n"` and explicit `encoding="utf-8"`, or the ledger gets CRLF-corrupted and reports render mojibake.
- **`gh` holds `repo` scope**, so every `gh` write must pass through `git_guard` with an allowlisted target slug.