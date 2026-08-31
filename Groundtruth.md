# Groundtruth

**An autonomous multi-agent system that keeps a Jira board honest.**

Project root: `D:\MIT\Agentic Jira` · Python 3.13 · Real Jira Cloud \+ GitHub

---

# Part I — The Idea

## The thesis

> Jira records what a team *believes* is happening. Git records what is *actually* happening. The gap between those two is a project manager's entire job — and nobody automates it.

Every engineering organisation runs two systems of record and they drift apart within days:

- A ticket sits "In Progress" for three weeks with zero commits on its branch.  
- A pull request merges while its ticket stays open forever.  
- Real work happens on a branch nobody ever filed a ticket for.  
- A ticket is marked "Done" with acceptance criteria that were never tested by anything.  
- The same feature exists as three tickets filed by three people.

Reconciling this is manual, weekly, and endless. A PM opens twenty browser tabs, cross-references commit history against a board, chases four people on Slack, and writes it all up for stakeholders. Then does it again next week.

**Groundtruth automates that loop** — and it can prove every claim it makes.

## What it does

A crew of four specialist agents over a shared governance layer.

### 1\. Intake Analyst

Turns raw input — meeting notes, a spec, a bug report, a pasted Slack thread — into properly-formed backlog items: Given-When-Then acceptance criteria, story points, components, declared dependencies.

Two behaviours make it more than a formatter:

- A **Definition-of-Ready gate** that *refuses* to file tickets which aren't ready, with machine-readable reasons (`NO_AC`, `AC_MALFORMED`, `NO_POINTS`).  
- **Duplicate detection** against the existing board — proposed, never auto-resolved.

### 2\. Board Steward ★ *the differentiator*

Continuously diffs Jira against Git and GitHub, emitting a `Discrepancy` for each finding with **hard evidence attached**: commit SHAs, PR numbers, CI conclusions, changelog timestamps.

| Detector | Finding |
| :---- | :---- |
| `STALE_IN_PROGRESS` | In Progress, no commit on a linked branch inside the staleness window |
| `MERGED_PR_TICKET_OPEN` | PR merged, ticket still open |
| `ORPHAN_BRANCH` | Branch with real commits, no corresponding ticket |
| `UNVERIFIED_NO_MAPPING` | Ticket's acceptance criteria bind to no test at all |
| `UNVERIFIED_MAPPING_STALE` | Binding exists but the test no longer exists |
| `UNVERIFIED_TEST_FAILING` | Bound test is failing, yet the ticket claims Done |
| `DUPLICATE_SUSPECTED` | Deterministic similarity over an open board — proposal only |

**This layer uses no LLM at all.** Whether PR \#142 is merged is a fact, not a judgment.

> **Why `UNVERIFIED` splits three ways.** Legacy tickets have no test binding simply because no agent ever ran on them. A single detector would flag 100% of them — grading your own seed data rather than the codebase. `NO_MAPPING` is reported as *coverage-of-mapping*, a baseline. Only `MAPPING_STALE` and `TEST_FAILING` are per-ticket defects.

### 3\. Delivery Agent

Takes one ready ticket and closes it out — with the order deliberately inverted from how coding agents usually work:

1. Create an isolated feature branch.  
2. **Write the tests from the acceptance criteria first**, and *prove they fail* — an assertion failure, not an import error.  
3. Implement until green, inside a bounded repair loop.  
4. Open a PR whose traceability matrix is **generated from real pytest JSON output**.

Writing tests first is what makes the repair loop meaningful: there is something real to fix. And if the loop exits without green, **the PR opens as a draft with the failing matrix shown honestly.** Never fabricate green.

### 4\. Reporting Agent

The standup digest, sprint health summary, and score-delta narrative — the writing chore, over numbers that were computed deterministically before any prose was generated.

*Stretch:* **Sprint Planner** — velocity-based capacity, dependency topological sort, load balancing.

## The governance layer

Cross-cutting, and the reason this is credible rather than a toy:

- **Hash-chained run ledger.** Append-only JSONL. Every action, its evidence, its approval, its outcome. `prev_hash`/`this_hash` make it tamper-evident — you can verify no entry was edited after the fact.  
- **Idempotency.** Reruns never duplicate tickets, keyed on content rather than on a summary string a model might rephrase.  
- **Propose → apply.** Default mode is dry-run. Applying requires the exact changeset hash, so approval binds to reviewed content.  
- **A safety envelope** that makes destructive git operations structurally impossible, not merely discouraged.

## The headline metric: Board Truthfulness Score

One number, 0–100, from five independently-reported dimensions. The demo shows it climb, with **every point itemised against an artifact the system did not produce itself.**

---

# Part II — Why this is a strong hackathon idea

## 1\. It sidesteps the most crowded category

The default agentic-engineering submission is *requirements in, pull request out*. Judges will see many of those. They are also competing against Devin, Copilot Workspace, Cursor's agents, and every YC AI-devtools company — so the implicit question is always "why is your weekend build better than a funded team's?"

Groundtruth answers a different question. It automates **the project manager**, not the developer. That space has almost no consumer-grade tooling, the pain is universal and instantly recognisable, and there is no obvious incumbent for a judge to compare you against.

Crucially, code generation still appears in the demo — as *one member of a crew* rather than the whole pitch. You get the visual payoff of an agent writing code without the burden of claiming to out-engineer Devin.

## 2\. The pain is legible in one sentence

A judge has maybe forty seconds of patience before deciding whether to care. Compare:

- ✗ "Our multi-agent system orchestrates PRD decomposition into verified implementations."  
- ✓ "Your Jira board is a story your team tells itself. We check it against Git and fix the parts that aren't true."

Anyone who has run a sprint feels the second one immediately. No domain explanation needed.

## 3\. It has a real number, and the number can survive scrutiny

Most hackathon projects are judged on vibes because there is nothing to measure. Groundtruth ships a **Board Truthfulness Score** that goes from a baseline to a higher number, with an itemised evidence log for every point gained.

Four design properties keep a skeptic from dismantling it — this is the part most metrics get wrong:

1. **Externally witnessed.** Every point cites something the system didn't generate: a commit SHA, a PR number, a **CI check-run conclusion**. Not our own local test run.  
2. **Frozen policy.** Weights live in a version-controlled file, hashed into every score record, committed *before* the demo data was written.  
3. **Falsifiable.** A shipped anti-gaming test suite proves cosmetic changes cannot raise the score.  
4. **Held-out.** A separate **control-group score** covers tickets the Delivery Agent never touched. If only the touched subset improves, the demo says so out loud.

## 4\. The demo's best moments are refusals

This is the strategic insight. Almost every submission demos an agent *doing* something. Very few demo an agent **declining** to do something — and refusal is the entire reason an organisation would let this near a real board.

Two beats:

- The system attempts `git add .` inside a repository rooted at a developer's home directory and is **blocked**, with a ledger entry.  
- An adversarial patch that deletes a failing assertion to force tests green is **rejected**, with the file restored byte-for-byte.

Both are memorable, both take under fifteen seconds, and both are the kind of thing a judge repeats to another judge afterwards.

## 5\. "No LLM here" is a feature, and it pre-empts the obvious attack

Every AI project gets asked about hallucination. Most answers are hedges about prompting and temperature.

This one has an architectural answer: reconciliation contains **zero model calls**, because merge status is a fact. The LLM is confined to exactly three places where language genuinely is the problem — parsing prose into stories, writing code, and writing prose. Being able to say *"we don't use a model where determinism is correct"* signals engineering judgment more strongly than any feature.

## 6\. It cannot be broken by the venue

Everything runs in a **replay mode** driven by fixtures captured from real Jira and GitHub calls. The demo runs offline with real recorded payloads. Dead conference Wi-Fi, an expired token, or an API rate limit cannot zero the presentation.

More submissions die to network problems on stage than to bad ideas. Rehearse with the network physically disabled.

## 7\. The build order fails gracefully

The differentiator (Steward \+ Score) is built **before** the fragile part (Delivery). If Delivery slips, there is still a complete, credible demo. Built in the opposite order, a slip leaves nothing. Every phase has its own demoable checkpoint and an explicit cut list.

## 8\. It maps onto how hackathons actually score

| Typical criterion | What carries it |
| :---- | :---- |
| Innovation | Board-vs-reality reconciliation; automating the PM rather than the dev |
| Technical depth | Hash-chained ledger, AST-level repair integrity, collect-only trace validation, record/replay |
| Completeness | Four working agents, real integrations, CLI, test suite |
| Impact | Universally recognised pain, quantified with a control group |
| Presentation | A number that climbs, evidence you can click, two refusal moments |
| Responsible AI | Deterministic where facts matter; human approval on every write; honest failure paths |

That last row is usually an afterthought bolted on at judging time. Here it *is* the architecture.

## The pitch, three ways

**One sentence.**

> Your Jira board is a story your team tells itself. Groundtruth checks that story against Git and fixes the parts that aren't true.

**Sixty seconds.**

> Every org runs two systems of record. Jira holds intent, Git holds reality, and they drift within days. Reconciling them is the unglamorous core of a PM's week — chasing whether a ticket is really in progress, whether a merged PR ever closed anything, whether "Done" was ever verified by a test.  
>   
> Groundtruth closes that gap with a crew of agents. An Intake Analyst turns raw meeting notes into properly-formed tickets and refuses the ones that aren't ready. A Board Steward diffs the board against the repository and reports every discrepancy with a clickable commit SHA or PR link. A Delivery Agent picks up a ready ticket and writes the tests from its acceptance criteria *first*, proves they fail, then codes until they pass. A Reporting Agent writes the standup nobody wants to write.  
>   
> The constraint that makes it credible: **it ships nothing it cannot prove.** Every discrepancy it reports and every point of its score traces to an artifact it did not produce itself.

**The questions you will be asked.**

*"How is this not Devin or Copilot Workspace?"* Those automate the developer. This automates the project manager, and its core loop uses no LLM at all — merge status is a fact, not a judgment.

*"How do I know it isn't inventing discrepancies?"* A `Discrepancy` cannot be constructed without at least one piece of evidence; a schema validator enforces it. Every item is a link you can click.

*"Isn't your score circular — you define the problems, then grade yourself on fixing them?"* Fair, and it's why the score is built four specific ways: every dimension cites an artifact the system didn't produce (CI check-run conclusions, not our own pytest runs); weights are frozen in a hashed policy file committed before the demo data existed; an anti-gaming suite proves cosmetic changes can't raise it; and we report a control-group score over tickets the Delivery Agent never touched.

*"What stops the model writing a passing test instead of fixing the bug?"* Six structural layers, not a prompt instruction. Test files are hash-locked and read-only during repair, the write path is partitioned to `src/` only, and assertion density is measured via AST and must not decrease.

**Say this unprompted:** if Delivery can't reach green, the PR opens as a draft with the failing matrix shown honestly. Volunteering that you kept the honest-failure path persuades more than any success demo.

---

# Part III — How to implement it

## Architecture

Deterministic spine. The LLM is called at **exactly three hops**, each isolated behind `adapters/llm.py`:

- **(a) Intake** — raw prose → structured stories  
- **(b) Delivery** — test authoring, implementation, repair  
- **(c) Reporting** — prose over already-computed numbers

Everything else — reconciliation, scoring, idempotency, traceability, safety — is plain code.

### Run modes

`LIVE` · `RECORD` · `REPLAY`. Every API response persists as a fixture keyed by request hash. **The demo runs `REPLAY` from a `LIVE` capture taken beforehand** — real recorded payloads, zero network dependency. This is the single highest-leverage risk decision in the plan.

### Layout

D:/MIT/Agentic Jira/               \# project root (space is intentional)

├─ pyproject.toml                  \# pinned deps, pytest config, console\_scripts

├─ .gitignore                      \# written BEFORE git init

├─ scoring\_policy.yaml             \# weights \+ policy\_version — FROZEN in Phase 1

├─ .env.example                    \# variable names only, never values

├─ README.md

├─ src/groundtruth/

│  ├─ \_\_main\_\_.py                  \# CLI: intake|audit|deliver|report|score|seed|reset

│  ├─ config.py                    \# env load, RunMode, fail-fast validation

│  ├─ clock.py                     \# Clock protocol; SystemClock / FrozenClock

│  ├─ ids.py                       \# idempotency keys, slugs

│  ├─ contracts/                   \# pure models, zero I/O

│  │  └─ story.py discrepancy.py ledger.py score.py trace.py testrun.py

│  ├─ ledger/

│  │  ├─ writer.py                 \# append-only JSONL, hash-chained, fsync

│  │  └─ reader.py                 \# replay \+ state projection

│  ├─ safety/

│  │  ├─ workspace.py          ★   \# WorkspaceGuard — repo-root assertion

│  │  ├─ git\_guard.py          ★   \# ONLY module permitted to invoke git

│  │  ├─ approval.py               \# propose → apply, bound to changeset hash

│  │  └─ redact.py                 \# secret scrubbing

│  ├─ adapters/

│  │  ├─ base.py                   \# record/replay envelope, request hashing

│  │  ├─ jira.py                   \# REST v3 — see /search/jql migration note

│  │  ├─ github.py                 \# gh CLI wrapper, arg-lists only

│  │  ├─ gitlog.py                 \# read-only history queries

│  │  ├─ pytest\_runner.py          \# subprocess pytest → TestRunResult

│  │  └─ llm.py                    \# 3 named prompts, cached by input hash

│  ├─ agents/

│  │  └─ intake.py steward.py delivery.py reporting.py planner.py

│  ├─ detectors/                   \# one file per rule, each pure(state) → Discrepancy\[\]

│  │  └─ stale.py merged\_open.py orphan\_branch.py unverified.py duplicate.py

│  ├─ delivery/

│  │  ├─ test\_author.py            \# AC → pytest file \+ manifest entries

│  │  ├─ red\_gate.py           ★   \# proves failure is assertion-based

│  │  ├─ test\_lock.py          ★   \# tests immutable during repair

│  │  ├─ repair.py                 \# bounded loop, src/ only

│  │  └─ pr\_body.py                \# matrix from real TestRunResult

│  ├─ scoring/

│  │  └─ dimensions.py score.py evidence\_log.py

│  ├─ trace/

│  │  └─ manifest.py reconcile.py

│  └─ seed/

│     └─ seed\_jira.py seed\_git.py reset.py scenario.yaml

├─ workspace/                  ★   \# sandbox: the ONLY git-writable tree

├─ artifacts/                      \# run\_\*/ ledger.jsonl, pytest.json, score.json

└─ tests/

   ├─ test\_detectors\_\*.py          \# golden fixtures per rule

   ├─ test\_score\_antigaming.py ★   \# the credibility suite

   ├─ test\_safety\_guard.py     ★   \# asserts refusal outside sandbox

   └─ test\_test\_lock.py        ★   \# asserts repair cannot mutate tests

★ \= load-bearing for safety or credibility. Build first; never allow a bypass.

## Data contracts

Pydantic v2, `extra="forbid"`, frozen where practical. These are the backbone — precision matters more here than anywhere else.

**`Evidence`** — discriminated union; every variant externally checkable. `kind: "commit"|"pr"|"check_run"|"jira_changelog"|"test_result"|"branch"` · `ref` (SHA / PR\# / node id) · `url` (clickable) · `observed_at` · `detail`

**`Discrepancy`** `discrepancy_id` \= sha256(type \+ subject \+ evidence refs), so it dedupes across runs · `type` · `severity` · `subject` · **`evidence: list[Evidence]` with a non-empty validator** · `proposed_action` · `detected_at` · `as_of` (pinned clock) · `detector_version`

> The non-empty evidence validator is the whole thesis in one line: *a discrepancy that cannot cite evidence cannot be constructed.*

**`ProposedAction`** — `verb: TRANSITION|COMMENT|LINK|CREATE_TICKET|CLOSE_DUPLICATE|NONE` · `target` · `params` · `reversible` · `requires_approval: bool = True` (never defaulted False)

**`Story`** — `idempotency_key` \= sha256(source\_doc\_id \+ normalized AC text) · `jira_key: str|None` · `summary` · `description` · `acceptance_criteria` · `points` · `components` · `depends_on` · `status` · `dor: DefinitionOfReadyResult` · `source: ProvenanceRef` (doc id \+ char span \+ llm\_call\_id) · `dedupe: DedupeVerdict|None`

> **Never key idempotency on summary text** — a model rephrasing a summary silently double-creates the ticket. The key is written to a Jira label and mirrored in local state.

**`AcceptanceCriterion`** — `ac_id` \= `"{story_key}-AC{n}"`, stable across rewording · `given`/`when`/`then` · `raw` · `is_wellformed`

**`DedupeVerdict`** — `candidate_jira_keys` · `similarity` · `method` · `threshold` · `human_confirmed: bool|None`. Duplicates enter the score **only after human confirmation**, so a model's judgment never moves the headline number.

**`LedgerEntry`** — `seq` · `run_id` · `ts` · `actor` · `action` · `mode: PROPOSE|APPLY|DRY_RUN|REPLAY` · `subject` · `inputs_hash` · `outputs_hash` · `evidence` · `approval` (required when mode=APPLY and the action writes) · `outcome: ok|refused|error` · **`prev_hash` / `this_hash`**

> The hash chain is a few lines of code and converts the ledger from *a log* into *a tamper-evident record*. Do not skip it.

**`TraceLink`** — `ac_id` · `test_node_id` (exact pytest nodeid) · `bound_by: "manifest"` · `bound_at` · `test_file_hash`

**`TraceMatrixRow`** — `ac_id` · `ac_text` · `test_node_ids` · `status: passed|failed|missing|error|skipped|not_collected` · `red_proof` · `evidence`

**`RedProof`** — `node_id` · `failed_at` · `failure_kind: assertion|import_error|collection_error` · `longrepr_excerpt`

**`TestRunResult`** — parsed from `pytest-json-report`, never hand-built. `tests: dict[node_id, TestOutcome]` · `collected_node_ids` (detects stale mappings) · `raw_report_path` (artifact retained for inspection)

**`DimensionScore`** — `name` · `value: float|None` · `numerator` · `denominator` · `weight` · `evidence` · `excluded_reason`

**`TruthfulnessScore`** — `total` · `dimensions` · `policy_version` · `policy_hash` · `as_of` · `board_snapshot_hash` · `control_group` · `evidence_log_path`

## The Board Truthfulness Score

Five dimensions, each in \[0,1\], each reported as **numerator/denominator — never a bare float**.

| Dimension | Definition | External witness |
| :---- | :---- | :---- |
| `ac_validity` | tickets whose ACs parse as well-formed G-W-T and pass DoR | deterministic parser, no LLM |
| `progress_integrity` | of In Progress: ≥1 commit within the staleness window on a branch linked to the key | commit SHA \+ author date |
| `done_integrity` | of Done: merged PR **and** passing CI check-run on the merge SHA | PR number \+ check-run conclusion |
| `staleness_health` | 1 − (weighted stale-days / cap) across active tickets | Jira changelog timestamps |
| `duplication_health` | 1 − (human-confirmed duplicate pairs / active tickets) | ledger approval entry |

`done_integrity` cites the **GitHub Actions check-run conclusion** for the merged SHA via `gh api` — *not* our own pytest run. Locally-run tests are self-attestation. Local pytest is evidence for the **PR body**; CI conclusion is evidence for the **score**. Never conflate them.

Unmeasurable dimensions score `null` and are **excluded from the denominator, with the exclusion printed.** Silently scoring a missing dimension as 1.0 is the most common way metrics like this lie.

**Do not pre-announce a target number.** Report whatever it lands on. A judge trusts 41 → 78 with an itemised evidence log far more than a suspiciously round 92 — and a pre-committed target reads as a fitted result, undermining the exact evidence log it exists to showcase.

## AC-to-test traceability

**Recommendation: a generated `trace_manifest.json` as sole authority, cross-validated against real pytest node ids, with a non-authoritative marker for readability.**

| Option | Verdict |
| :---- | :---- |
| Naming convention (`test_AC1_…`) | Reject — brittle, breaks on refactor/parametrize, encodes no AC text |
| Docstring parsing | Reject as authority — drifts silently with no failure signal |
| `@pytest.mark.ac("KEY-AC2")` | Keep as *secondary*. Survives renames, but lives inside a file the repair loop may touch |
| **Manifest \+ node-id validation** | **Recommend** — external to test files, diffable, stores `test_file_hash`, supports many-to-many |

Mechanism:

1. `test_author.py` writes the test file **and** `TraceLink` entries with `ac_id`, intended `test_node_id`, `test_file_hash`.  
2. **Validation is mandatory.** Run `pytest --collect-only -q --json-report`; every manifest node id must appear in `collected_node_ids`. A manifest entry pointing at a nonexistent node is a **hard error**, never a silent skip. *This is what makes the matrix real: the binding is proven against pytest's collector, not asserted by its generator.*  
3. Marker emitted alongside; disagreement is flagged, manifest wins.  
4. `reconcile.py` joins manifest × `TestRunResult` → `TraceMatrix`. **An AC with no link renders `missing`, not omitted** — the PR body must show its own gaps.

Every checkbox in a PR body is therefore a function of a node id's outcome in a stored pytest JSON artifact. The manifest is committed, so it appears in the PR diff and a reviewer sees claimed bindings change.

## Repair-loop integrity

The classic failure of self-healing agents is deleting the failing assertion to force green. Core principle: **do not ask the model not to edit tests — make test edits mechanically impossible to commit.** Six layers:

1. **Hash lock.** sha256 of every test file \+ manifest recorded before repair, re-hashed after *every* iteration. Mismatch → revert from the locked copy, abort iteration, write a `refused` ledger entry (`TEST_MUTATION_ATTEMPT`). Not a warning.  
2. **Write-path partition.** Repair is granted `src/` only. `tests/` and `trace_manifest.json` are owned by `test_author.py`, which does not run during repair. Enforced in the file-writing primitive, not the prompt.  
3. **Read-only posture.** Test files set `stat.S_IREAD` during the repair window.  
4. **Collection monotonicity.** `len(collected_node_ids)` must never decrease, and every AC-bound node must stay collected. Catches deletion, rename, and injected `@pytest.mark.skip`.  
5. **Skip/xfail ban.** Post-repair scan for newly added `skip`, `xfail`, `pytest.raises` wrapping the asserted call, or `assert True` in bound tests.  
6. **Assertion-density floor.** Assertion count per bound test recorded via `ast` at lock time; must not decrease. Blocks assertion *weakening*, which hashing catches but semantic review may not.

Bounded at 3 iterations, with a per-iteration diff written to the ledger so the loop's full history is inspectable. If it exits without green, **the PR opens as a draft with the failing matrix shown honestly.**

## Safety envelope

### Git — structurally impossible, not merely discouraged

The hazard class this defends against is real and severe: a coding agent running `git add .` inside a repository whose root is a developer's home directory will stage private keys, cloud credentials, and Docker/Kubernetes config. With a `gh` token holding `repo` scope, the next push **publishes them**. This is not hypothetical on the target machine — the Windows home directory is itself an uncommitted git repository with no `.gitignore`.

1. **No ambient repo, ever.** All git writes target an explicit sandbox path. No code path runs a git write with inherited `cwd`.  
2. **`WorkspaceGuard`, checked on every git write call** — not once at startup: resolve realpath; `git rev-parse --show-toplevel` must equal the sandbox root *exactly*; root must resolve **under `allowed_root` \= `D:/MIT/Agentic Jira`**; root must contain a `.groundtruth-sandbox` sentinel carrying the run's workspace id; root must **never** be the user's home directory, a parent of it, or an ancestor of home; remote must match the expected demo repo or be explicitly local-only. **Fail closed** — any check erroring is a refusal.  
3. **Single choke point.** `safety/git_guard.py` is the only module permitted to invoke git, enforced by a repo test that greps for git subprocess calls outside it and fails.  
4. **Allowlist with forbidden argument forms.** Allow `init, checkout -b, add <explicit-paths>, commit -m, push, rev-parse, log, status, diff, branch, show`. **Hard-ban** `add .`, `add -A`, `add -u`, `commit -a`, `clean`, `reset --hard`, `checkout .`, `push --force`, and any pathspec that is `.`, absolute, or contains `..`. `shell=True` rejected entirely.  
5. **`GIT_DIR` / `GIT_WORK_TREE` pinned** explicitly in the subprocess env on every write, so git cannot walk up and discover an enclosing repo even if cwd is wrong.  
6. **`.gitignore` written before `git init`.** Never `git init` outside the sandbox.  
7. **Blocking preflight** detects a repo rooted at the home directory and prints loud remediation. It **never remediates automatically** — that is user data.  
8. **`gh` through the same guard.** `gh repo create` and `gh pr create` route through `git_guard` with an allowlisted target slug. A push to an unexpected repo is refused. This closes the credential-publication path.

### Secrets

Credentials only from env / gitignored `.env`; `.env.example` holds names only. Fail fast listing missing *names*, never values. `redact.py` scrubs `gho_`, `ghp_`, `ATATT`, JWT-shaped, and `Bearer` patterns on every ledger write, report render, and LLM prompt — and is itself tested. Tokens and raw `.env` never enter a prompt. The seeder refuses to run against any Jira project key other than the configured demo key.

### Approval

`propose` emits a `ChangeSet` to `artifacts/`. `apply` **requires the changeset hash as an argument**, so approval binds to exact reviewed content and a changeset cannot mutate between review and apply. Default mode is `DRY_RUN`; `APPLY` needs both an explicit flag and the hash.

## Build order

Each phase ends at a demoable checkpoint. Cut annotations are load-bearing.

**Phase 0 — Safety and skeleton.** Scaffold at `D:\MIT\Agentic Jira` (empty, outside any repo). Venv; pin `pytest`, `pytest-json-report`, `pydantic`, `httpx`, `pyyaml` (**none currently installed — pytest included**). Build `contracts/`, `clock.py`, hash-chained ledger, `WorkspaceGuard`, `git_guard`, `test_safety_guard.py`. → *Checkpoint:* a script attempts `git add .` from the home directory and is **refused** with a ledger entry. This is demo beat 1\. Assert the guard also works through the space in the project path. → *Cut:* nothing.

**Phase 1 — Seeder \+ Steward \+ Score.** The differentiator, before Delivery. `seed_jira.py` / `seed_git.py` from `scenario.yaml`; the detectors with golden-fixture tests; `scoring/` with `scoring_policy.yaml` **frozen now**; `test_score_antigaming.py`. → *Checkpoint:* `groundtruth audit` prints discrepancies with clickable evidence plus a baseline score with itemised log. → *Cut:* `duplicate.py` first (needs human adjudication anyway); `unverified.py` can ship `NO_MAPPING`\-only.

**Phase 2 — Record/replay adapters.** `adapters/base.py` envelope; Jira read, `gh` wrapper, `gitlog`. Capture a `LIVE` run into fixtures. → *Checkpoint:* full audit runs offline in `REPLAY` against real recorded payloads. De-risks the stage entirely. → *Cut:* `RECORD` ergonomics, never the mode itself.

**Phase 3 — Intake \+ DoR gate.** LLM hop (a); `ids.py` idempotency; DoR gate; dedupe candidates as proposals only. → *Checkpoint:* messy notes → structured stories; a malformed ticket **refused** with reasons; rerun creates zero duplicates. → *Cut:* embedding similarity → token-set only.

**Phase 4 — Delivery Agent.** Highest effort, highest fragility. `test_author`, manifest \+ collect-only validation, `red_gate`, `test_lock`, bounded `repair`, `pr_body`. → *Checkpoint:* one ticket → branch → proven red → green → PR with real matrix; adversarial patch refused. → *Cut, in order:* multi-ticket → single scripted ticket; repair 3 → 1 iteration; if desperate, ship red-proof plus an honest draft PR with a failing matrix **and say so**.

**Phase 5 — Reporting \+ score narrative.** LLM hop (c) for prose over deterministic numbers; before/after score with evidence log and control-group figure. → *Checkpoint:* the score climb, itemised. → *Cut:* risk register, stakeholder status. Keep standup digest \+ score delta.

**Phase 6 — Stretch: Sprint Planner.** Cut without hesitation.

**Global cut priority:** Planner → risk register → duplicate detection → repair iterations → live mode (keep replay) → Delivery multi-ticket. **Never cut:** Phase 0 safety · hash-chained ledger · evidence-bearing `Discrepancy` · anti-gaming tests · honest matrix generation.

## Verification

1. **Safety.** From the home directory, invoke each banned git form (`add .`, `add -A`, `commit -a`, `push --force`) → all refused, each with a `refused` ledger entry. Assert the home repo's index is byte-identical before and after the whole suite.  
2. **Ledger integrity.** Recompute the hash chain over `ledger.jsonl`; tamper with one line and assert verification fails.  
3. **Detectors.** Golden fixtures per rule with hand-verified expected output. Assert every emitted `Discrepancy` has non-empty evidence, and that constructing one without evidence raises.  
4. **Score credibility.** Anti-gaming suite: closing a ticket with no PR must not raise the score; adding `assert True` must not raise it; deleting a stale ticket must raise it *less* than fixing it. Assert null dimensions are excluded from the denominator with the exclusion rendered, and `policy_hash` present in every record.  
5. **Idempotency.** Run `intake` twice on the same document against a live Jira project → exactly N tickets, not 2N. Rerun with a model-rephrased summary → still N.  
6. **Traceability.** Assert every manifest node id appears in `--collect-only` output; delete a test and assert `MAPPING_STALE` is raised rather than silently skipped; assert an unbound AC renders `missing` in the PR body.  
7. **Repair integrity.** Adversarial patches — delete an assertion; add `@pytest.mark.skip`; replace a body with `assert True`; edit the manifest — each refused with a ledger entry, files byte-identical afterwards.  
8. **CLI surface.** Each command (`intake|audit|deliver|report|score|seed|reset`) run for real; assert exit codes, and that `DRY_RUN` is the default and produces zero writes.  
9. **End-to-end.** Seed → audit → intake → deliver → report → score, in `REPLAY` and once in `LIVE`. In `LIVE`, verify by hand: open the Jira ticket, open the PR, click a cited SHA, confirm the check-run conclusion matches what the score claims.  
10. **Full dress rehearsal** of the demo, in `REPLAY`, with the network **physically disabled**. This is the real gate.

## Known gotchas (verified)

- **Jira JQL search migrated.** `GET`/`POST /rest/api/3/search` are deprecated → **`/rest/api/3/search/jql`**, and `fields` must now be specified explicitly (e.g. `fields=*all`). The new API also drops `total`, so **score denominators require paginating to completion** via `nextPageToken` (or an approximate-count endpoint — confirm during Phase 2). Issue creation and transition endpoints are unaffected.  
- **Jira transitions are workflow-specific.** Transitioning to a status name throws if the board's workflow lacks that transition. Always resolve transition ids from the transitions endpoint and fail with the available list rather than a bare error.  
- **`pytest` is not installed** on this machine, nor `pydantic` or a JSON reporter. The entire traceability mechanism depends on machine-readable pytest output — pin `pytest` \+ `pytest-json-report` in Phase 0 (fallback: `--junit-xml`).  
- **Windows.** `gh` via arg-lists with `shell=False`; `pathlib` throughout; JSONL written with `newline="\n"` and explicit `encoding="utf-8"` or the ledger gets CRLF-corrupted and reports get mojibake.  
- **Space in the project path.** `D:\MIT\Agentic Jira` contains a space, so never interpolate the path into a command string, and pass `GIT_DIR`/`GIT_WORK_TREE` as env values. Add a Phase 0 test exercising the git guard through the real spaced path rather than a temp dir without one — otherwise the bug surfaces first on stage.  
- **Cross-volume.** Project on `D:`, working directory on `C:`. `os.path.relpath` raises `ValueError` across drives on Windows, so any path-relativization must use `Path.is_relative_to`.  
- **Red proof must be assertion-based.** A test importing a nonexistent module trivially "fails first" while testing nothing. `red_gate` requires `outcome == failed` with a non-collection failure, or records the weaker `RED_VIA_IMPORT_ERROR` class, which must convert to a real assertion failure once the module skeleton exists.  
- **Staleness needs an injected clock.** Wall-clock `now()` makes scores non-reproducible between rehearsal and stage, and rots fixtures. `REPLAY` pins `as_of` to the recorded run timestamp; every score is stamped with the `as_of` it was computed against.

---

# Part IV — The demo script

Five minutes, run in `REPLAY`, network disabled.

| \# | Beat | Time | What the audience sees |
| :---- | :---- | :---- | :---- |
| 1 | **The loaded gun** | 0:30 | A command attempts `git add .` inside a repo rooted at a home directory. **Refused**, with a ledger entry. Opens on safety and proves the system has teeth. |
| 2 | **The messy board** | 0:30 | Seeded Jira board and matching repo history. Baseline score with itemised evidence. |
| 3 | **Steward audit** | 1:30 | Discrepancies stream out, each with a clickable SHA or PR link. *"AUTO-14 is In Progress; the last commit on its branch was nine days ago — here it is."* |
| 4 | **Intake** | 0:45 | Raw meeting notes → structured tickets with Given-When-Then. One malformed ticket **refused** with reasons. Rerun creates zero duplicates. |
| 5 | **Delivery** | 1:00 | One ticket: branch → tests fail (red, proven) → implementation → green → PR whose matrix comes from real pytest JSON. Then an adversarial patch deleting a failing assertion is **refused**. |
| 6 | **The number** | 0:45 | Score climbs, every point itemised. Anti-gaming suite runs live: closing a ticket with no PR does *not* raise it. |

**Beats 1 and 5-adversarial are what win it.** Anyone can demo an agent doing something. Almost nobody demos an agent refusing to do something — and refusal is the entire reason an organisation would deploy this.  
