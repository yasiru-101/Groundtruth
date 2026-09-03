import { Activity, GitCommit, ShieldCheck } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AgentActivityFeed } from "@/components/agents/AgentActivityFeed"
import { RunTrigger } from "@/components/agents/RunTrigger"
import { DiscrepancyInbox } from "@/components/discrepancies/DiscrepancyInbox"
import { DimensionBreakdown } from "@/components/score/DimensionBreakdown"
import { ScoreGauge } from "@/components/score/ScoreGauge"
import { ScoreSparkline } from "@/components/score/ScoreSparkline"
import { useAgentsSummary } from "@/hooks/useAgents"
import { useDiscrepancies } from "@/hooks/useDiscrepancies"
import { useLedger } from "@/hooks/useLedger"
import { useScoreHistory, useScoreLatest } from "@/hooks/useScore"

export function Overview() {
  const score = useScoreLatest()
  const history = useScoreHistory()
  const discrepancies = useDiscrepancies()
  const agents = useAgentsSummary()
  const ledger = useLedger()

  const isLoading =
    score.isLoading || history.isLoading || discrepancies.isLoading || agents.isLoading || ledger.isLoading
  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading dashboard…</div>

  const error = score.error || history.error || discrepancies.error || agents.error || ledger.error
  if (error) return <div className="p-8 text-center text-rose-500">Failed to load dashboard.</div>

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-3">
        <Card className="md:col-span-1">
          <CardContent className="flex flex-col items-center justify-center py-8">
            <ScoreGauge value={score.data?.total ?? 0} />
            <p className="mt-4 text-xs text-muted-foreground mono">
              {score.data?.run_dir}
            </p>
          </CardContent>
        </Card>
        <div className="md:col-span-2">
          <DimensionBreakdown dimensions={score.data?.dimensions ?? []} />
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Open discrepancies</CardTitle>
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{discrepancies.data?.length ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Agent actions</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{agents.data?.total_actions ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Policy hash</CardTitle>
            <GitCommit className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="mono truncate text-xs">{score.data?.policy_hash.slice(0, 16)}…</div>
          </CardContent>
        </Card>
      </div>

      <RunTrigger />

      <div className="grid gap-4 md:grid-cols-2">
        <ScoreSparkline history={history.data ?? []} />
        <DiscrepancyInbox items={discrepancies.data ?? []} />
      </div>

      <AgentActivityFeed entries={ledger.data ?? []} limit={5} />
    </div>
  )
}
