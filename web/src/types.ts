export interface HealthResponse {
  status: string
  demo_mode: boolean
  artifacts_dir: string
}

export interface PolicyResponse {
  policy_hash: string
  policy_date: string
  policy_path: string
}

export interface DemoResponse {
  project_key: string
  run_count: number
  as_of: string | null
}

export interface ScoreDimension {
  name: string
  value: number | null
  weight: number
  raw: string
  evidence: Record<string, unknown>[]
}

export interface ScoreLatest {
  run_id: string
  run_dir: string
  project_key: string
  as_of: string
  total: number
  policy_hash: string
  board_snapshot_hash: string
  dimensions: ScoreDimension[]
  control_group: Record<string, unknown> | null
}

export interface ScoreHistoryPoint {
  run_id: string
  run_dir: string
  as_of: string
  total: number
  policy_hash: string
}

export interface DiscrepancyEvidence {
  kind: string
  ref: string
  url: string
  observed_at?: string
  detail: Record<string, unknown>
}

export interface ProposedAction {
  verb: string
  target: string
  params: Record<string, unknown>
  reversible: boolean
  requires_approval: boolean
}

export interface DiscrepancyItem {
  discrepancy_id: string
  type: string
  severity: string
  subject: string
  evidence: DiscrepancyEvidence[]
  proposed_action: ProposedAction
  detected_at?: string
  as_of?: string
  detector_version?: string
}

export interface AgentActivity {
  actor: string
  action_count: number
  last_action?: string
  last_subject?: string
  last_ts?: string
}

export interface AgentSummary {
  actors: AgentActivity[]
  total_actions: number
  refusals: number
}

export interface LedgerEntry {
  seq: number
  run_id: string
  entry_id: string
  ts: string
  actor: string
  action: string
  mode: string
  subject: string
  outcome: string
  error?: string
  evidence: Record<string, unknown>[]
}

export interface LedgerIntegrity {
  run_dir: string
  ledger_path: string
  valid: boolean
  entries: number
  error?: string
}

export interface RunSummary {
  run_id: string
  label: string
  run_dir: string
  created_at: string
  files: string[]
}

export interface SprintPlan {
  run_id: string
  run_dir: string
  project_key: string
  as_of: string
  velocity: number
  capacity: number
  total_selected_points: number
  total_candidate_points: number
  over_committed: boolean
  selected: Array<{
    key: string
    summary: string
    points: number
    assignee?: string
    depends_on: string[]
  }>
  unscheduled: Array<{
    key: string
    summary: string
    points: number
    assignee?: string
    depends_on: string[]
  }>
  assignments: Record<string, string[]>
  cycles: string[][]
}

export interface StandupReport {
  run_id: string
  run_dir: string
  project_key: string
  as_of: string
  prose: string
  markdown: string
  active_tickets: number
  open_discrepancies: number
  unverified_items: number
  stale_items: number
}

export interface DeliveryItem {
  run_id: string
  run_dir: string
  ticket_key: string
  branch: string
  phase: string
  green: boolean
  pr_url?: string
  head_sha?: string
  iterations: Record<string, unknown>[]
  refusals: string[]
}

export interface TraceBinding {
  ac_id: string
  test_node_id: string
  bound_by: string
  bound_at?: string
}

export interface TraceabilityMatrix {
  run_id: string
  run_dir: string
  bindings: TraceBinding[]
  snapshot: Record<string, unknown>
}

export interface JobStatus {
  job_id: string
  command: string
  status: string
  created_at: string
  finished_at?: string
  result?: Record<string, unknown>
  error?: string
}

export interface ScoreComparison {
  before: {
    run_id: string
    run_dir: string
    as_of: string
    total: number
    policy_hash: string
  }
  after: {
    run_id: string
    run_dir: string
    as_of: string
    total: number
    policy_hash: string
  }
  delta: number
  dimensions_changed: Array<{
    name: string
    before: number | null
    after: number | null
  }>
  resolved: string[]
  introduced: string[]
}

export interface ChangesetItem {
  hash: string
  description: string
  items: Record<string, unknown>[]
}
