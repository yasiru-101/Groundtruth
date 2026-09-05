# Groundtruth Dashboard UX Overhaul

## Context

The packaged `.exe` runs and serves the app, but first-time users cannot understand what Groundtruth does or how to navigate it. The worst symptom is the Overview page: if no score data exists, it shows a single red `Failed to load dashboard.` and hides everything else. Navigation is incomplete (`/runs` exists but has no sidebar link), pages have no titles, demo mode is unexplained, and action labels like "Live replay" are misleading. This plan fixes those issues with frontend-only changes.

## Goals

1. Make the app explain itself to a first-time user.
2. Fix navigation (add missing links, mobile support, page titles, 404 page).
3. Replace dead-end errors with useful empty states and retry UI.
4. Make demo vs. live data unmistakable.
5. Clarify the primary action and unify job status across pages.

## Recommended approach (phased)

### Phase 1 — Navigation & page structure

- **New `web/src/lib/nav.ts`** — single source of truth for routes, labels, icons, page titles, and descriptions.
- **`web/src/components/layout/Sidebar.tsx`** — render from `nav.ts`, add the missing `/runs` link, and add group labels.
- **New `web/src/components/layout/MobileNav.tsx`** — hamburger drawer for screens below `md`. Reuses `ui/sheet.tsx` (may need a `side` prop).
- **New `web/src/components/layout/PageHeader.tsx`** — `title` + `description` + optional `actions`. Added to all pages.
- **`web/src/components/layout/Topbar.tsx`** — make logo link to `/`, add hamburger slot, tagline, help trigger, and connection status dots.
- **New `web/src/pages/NotFound.tsx`** + **`web/src/App.tsx`** — add `path="*"` route inside the layout.
- **New `web/src/hooks/useDocumentTitle.ts`** — sets `document.title` from `nav.ts` per route.

### Phase 2 — Resilience & empty states

- **`web/src/lib/api.ts`** — introduce `ApiError` with `status` and parse FastAPI `{ detail }` bodies, so 404 "no data yet" can be distinguished from real failures.
- **New `web/src/lib/query.ts`** — helpers `isNotFound(err)` and a retry predicate that skips 404s.
- **New `web/src/components/ui/skeleton.tsx`**, **`web/src/components/common/EmptyState.tsx`**, **`web/src/components/common/ErrorState.tsx`**, **`web/src/components/common/ErrorBoundary.tsx`**.
- **`web/src/pages/Overview.tsx`** — remove the two page-wide loading/error gates. Each section owns its own state: skeleton while loading, empty state on 404, error state with Retry for other errors.
- Apply the same per-section pattern to `Discrepancies.tsx`, `Agents.tsx`, `Report.tsx`, `Integrity.tsx`, `Runs.tsx`.
- **New toast system** (`web/src/components/ui/toast.tsx` + `web/src/hooks/useToast.tsx`) for Settings saves and job completion/failure.

### Phase 3 — Explain the product

- **New `web/src/components/onboarding/WelcomeCard.tsx`** — dismissible card for the top of Overview explaining what Groundtruth does in three plain sentences, with CTAs to Discrepancies, Integrity, and Settings. Dismissal persisted to `localStorage`.
- **New `web/src/components/onboarding/HelpDialog.tsx`** — reopened from the Topbar `?` icon; shows the welcome content plus a short glossary.
- **New `web/src/components/ui/info-hint.tsx`** — small info tooltip to attach to jargon terms (`Truthfulness score`, `Policy hash`, `Hash chain`, `Refusals`).
- Page descriptions land automatically through `PageHeader`.

### Phase 4 — Demo vs. live clarity

- **New `web/src/hooks/useSystemStatus.ts`** — combines `/api/health`, `/api/demo`, and `/api/connections` into one shared query for Topbar, banner, Settings, and Overview.
- **New `web/src/components/layout/DemoBanner.tsx`** — rendered in `AppShell` under the Topbar:
  - Demo + no connections: "Showing demo data. Connect GitHub and Jira in Settings."
  - Demo + connected: amber banner explaining that the dashboard is still reading the bundled demo snapshot and live runs are CLI-only.
  - Live mode: emerald banner naming the artifacts directory.
- **`web/src/components/layout/Topbar.tsx`** — three connection dots (GitHub / Jira / LLM) linking to Settings.
- **`web/src/pages/Settings.tsx`** — add a status summary card and explain what connecting actually enables.

### Phase 5 — Run action clarity

- **`web/src/components/agents/RunTrigger.tsx`**:
  - Retitle from "Live replay" to "Re-run analysis" with an honest subtitle.
  - Offer "Run audit" / "Run score" / "Run report" buttons with one-line hints.
  - Add `variant?: "card" | "inline"` so Overview can show a compact version.
- **New `web/src/components/jobs/JobProvider.tsx`** — lift `jobId` out of local state into context so Overview and Agents see the same running job.
- Deduplicate: Overview keeps an inline `RunTrigger` in its `PageHeader` actions; Agents keeps the full card.

### Phase 6 — Polish

- **`web/src/pages/Runs.tsx`** — add PageHeader, empty state, and short explanations of run labels.
- **New `web/src/components/score/ScoreVerdict.tsx`** — plain-English sentence next to the score gauge.
- Reorder Overview to: verdict + score → counters → discrepancies → activity.
- Verify mobile collapse and focus/accessibility on all pages.

## Critical files to modify

- `web/src/pages/Overview.tsx`
- `web/src/lib/api.ts`
- `web/src/components/layout/Sidebar.tsx`
- `web/src/App.tsx`
- `web/src/components/agents/RunTrigger.tsx`
- `web/src/hooks/useJobs.ts`
- `web/src/pages/Settings.tsx`
- `web/src/components/layout/Topbar.tsx`
- `web/src/components/layout/AppShell.tsx`

## Verification

1. Start the API (`python -m groundtruth.api`) and the Vite dev server (`cd web && npm run dev`).
2. With demo data: confirm every sidebar link works, `/runs` is reachable, page headers are visible, welcome card appears, and mobile nav works at 375px.
3. With an empty artifacts dir (`GT_API_ARTIFACTS_DIR=./empty_dir python -m groundtruth.api`): confirm Overview renders per-section empty states instead of `Failed to load dashboard.`
4. Stop the API: confirm `ErrorState` with a working Retry button.
5. Connect a GitHub PAT in Settings: confirm Topbar dot turns green and demo banner escalates to amber with the CLI-only message.
6. Start a job on Overview, navigate to Agents: confirm the same job status appears.
7. Run `cd web && npm run lint && npm run build` before testing the packaged executable.