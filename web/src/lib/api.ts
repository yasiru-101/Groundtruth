import {
  type AgentSummary,
  type DemoResponse,
  type DeliveryItem,
  type DiscrepancyItem,
  type HealthResponse,
  type JobStatus,
  type LedgerEntry,
  type LedgerIntegrity,
  type PolicyResponse,
  type RunSummary,
  type ScoreComparison,
  type ScoreHistoryPoint,
  type ScoreLatest,
  type SprintPlan,
  type StandupReport,
  type TraceabilityMatrix,
} from "@/types"

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api"

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { accept: "application/json" },
    ...init,
  })
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => fetchJson<HealthResponse>("/health"),
  policy: () => fetchJson<PolicyResponse>("/policy"),
  demo: () => fetchJson<DemoResponse>("/demo"),
  runs: () => fetchJson<RunSummary[]>("/runs"),
  scoreLatest: () => fetchJson<ScoreLatest>("/score/latest"),
  scoreHistory: () => fetchJson<ScoreHistoryPoint[]>("/score/history"),
  compareScore: (before: string, after: string) =>
    fetchJson<ScoreComparison>(`/score/compare?before=${encodeURIComponent(before)}&after=${encodeURIComponent(after)}`),
  discrepancies: (params?: { severity?: string; type?: string; subject?: string }) => {
    const qs = new URLSearchParams()
    if (params?.severity) qs.set("severity", params.severity)
    if (params?.type) qs.set("type", params.type)
    if (params?.subject) qs.set("subject", params.subject)
    return fetchJson<DiscrepancyItem[]>(`/discrepancies?${qs.toString()}`)
  },
  plan: () => fetchJson<SprintPlan>("/plan/latest"),
  report: () => fetchJson<StandupReport>("/report/latest"),
  reportMarkdown: () => fetch(`${API_BASE}/report/markdown`).then((r) => r.text()),
  delivery: () => fetchJson<DeliveryItem>("/delivery/latest"),
  trace: () => fetchJson<TraceabilityMatrix>("/trace/latest"),
  ledger: () => fetchJson<LedgerEntry[]>("/ledger"),
  ledgerIntegrity: () => fetchJson<LedgerIntegrity[]>("/ledger/integrity"),
  agents: () => fetchJson<AgentSummary>("/agents/summary"),
  submitJob: (command: string) =>
    fetchJson<JobStatus>("/jobs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command }),
    }),
  jobStatus: (id: string) => fetchJson<JobStatus>(`/jobs/${id}`),
}
