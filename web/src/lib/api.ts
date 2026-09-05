import {
  type AgentSummary,
  type ConnectionTestResult,
  type ConnectionsStatus,
  type DemoResponse,
  type DeliveryItem,
  type DiscrepancyItem,
  type HealthResponse,
  type JobStatus,
  type LedgerEntry,
  type LedgerIntegrity,
  type OAuthStartResponse,
  type ParsedUrlResponse,
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

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { accept: "application/json" },
    ...init,
  })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body && typeof body.detail === "string") {
        message = body.detail
      } else if (body && typeof body.message === "string") {
        message = body.message
      }
    } catch {
      // leave the default message
    }
    throw new ApiError(res.status, message)
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
  connections: () => fetchJson<ConnectionsStatus>("/connections"),
  parseUrl: (url: string) =>
    fetchJson<ParsedUrlResponse>("/connections/parse-url", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url }),
    }),
  setGitHubRepo: (owner: string, name: string) =>
    fetchJson<{ ok: boolean }>("/connections/github/repo", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner, name }),
    }),
  setGitHubPat: (owner: string, name: string, pat: string) =>
    fetchJson<{ ok: boolean }>("/connections/github/pat", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner, name, pat }),
    }),
  setJiraProject: (base_url: string, project_key: string) =>
    fetchJson<{ ok: boolean }>("/connections/jira/project", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ base_url, project_key }),
    }),
  setJiraBasic: (base_url: string, project_key: string, email: string, api_token: string) =>
    fetchJson<{ ok: boolean }>("/connections/jira/basic", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ base_url, project_key, email, api_token }),
    }),
  setLlm: (provider: string, base_url: string, model: string, api_key: string) =>
    fetchJson<{ ok: boolean }>("/connections/llm", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ provider, base_url, model, api_key }),
    }),
  testConnection: (provider: "github" | "jira" | "llm") =>
    fetchJson<ConnectionTestResult>(`/connections/${provider}/test`, {
      method: "POST",
    }),
  disconnect: (provider: "github" | "jira" | "llm") =>
    fetchJson<{ ok: boolean }>(`/connections/${provider}`, {
      method: "DELETE",
    }),
  oauthStart: (provider: "github" | "jira") =>
    fetchJson<OAuthStartResponse>(`/auth/${provider}/start`),
}
