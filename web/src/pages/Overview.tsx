import { Activity, AlertTriangle, GitCommit, LineChart, ShieldCheck } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/common/EmptyState"
import { ErrorState } from "@/components/common/ErrorState"
import { PageHeader } from "@/components/layout/PageHeader"
import { WelcomeCard } from "@/components/onboarding/WelcomeCard"
import { InfoHint } from "@/components/ui/info-hint"
import { AgentActivityFeed } from "@/components/agents/AgentActivityFeed"
import { RunTrigger } from "@/components/agents/RunTrigger"
import { DiscrepancyInbox } from "@/components/discrepancies/DiscrepancyInbox"
import { DimensionBreakdown } from "@/components/score/DimensionBreakdown"
import { ScoreGauge } from "@/components/score/ScoreGauge"
import { ScoreSparkline } from "@/components/score/ScoreSparkline"
import { ScoreVerdict } from "@/components/score/ScoreVerdict"
import { useAgentsSummary } from "@/hooks/useAgents"
import { useDiscrepancies } from "@/hooks/useDiscrepancies"
import { useLedger } from "@/hooks/useLedger"
import { useScoreHistory, useScoreLatest } from "@/hooks/useScore"
import { isNotFound } from "@/lib/query"

export function Overview() {
  const score = useScoreLatest()
  const history = useScoreHistory()
  const discrepancies = useDiscrepancies()
  const agents = useAgentsSummary()
  const ledger = useLedger()

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="How truthful the board is right now and what needs attention."
        actions={<RunTrigger variant="inline" />}
      />

      <WelcomeCard />

      {/* 1. Score & Dimensions */}
      {score.isLoading ? (
        <div className="grid gap-4 md:grid-cols-3">
          <Skeleton className="h-72 rounded-xl md:col-span-1" />
          <Skeleton className="h-72 rounded-xl md:col-span-2" />
        </div>
      ) : score.error ? (
        isNotFound(score.error) ? (
          <EmptyState
            icon={ShieldCheck}
            title="No score computed yet"
            description="Run analysis or replay a run to calculate the truthfulness score from Jira and Git artifacts."
            action={{ to: "/agents", label: "View agents & replay" }}
          />
        ) : (
          <ErrorState title="Failed to load score" error={score.error} retry={score.refetch} />
        )
      ) : (
        <div className="grid gap-4 md:grid-cols-3">
          <Card className="md:col-span-1">
            <CardHeader className="pb-2">
              <CardTitle className="text-base flex items-center justify-between">
                <span>Truthfulness</span>
                <InfoHint text="Weighted measure of how accurately Jira tickets represent Git activity. Dimensions with missing data are omitted, not assumed perfect." />
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center justify-center pt-2 text-center">
              <ScoreVerdict
                total={score.data?.total ?? 0}
                discrepancies={discrepancies.data ?? []}
              />
              <div className="my-4">
                <ScoreGauge value={score.data?.total ?? 0} />
              </div>
              {score.data?.run_dir && (
                <p className="text-xs text-muted-foreground mono">{score.data.run_dir}</p>
              )}
            </CardContent>
          </Card>
          <div className="md:col-span-2">
            <DimensionBreakdown dimensions={score.data?.dimensions ?? []} />
          </div>
        </div>
      )}

      {/* 2. Metric Counters */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div className="flex items-center gap-1.5">
              <CardTitle className="text-sm font-medium">Open discrepancies</CardTitle>
              <InfoHint text="Mismatches found between Jira issues and Git reality (e.g. unmerged PRs marked Done, missing PRs, stale issues)." />
            </div>
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {discrepancies.isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : discrepancies.error ? (
              <span className="text-sm text-destructive">Error</span>
            ) : (
              <div className="text-2xl font-bold">{discrepancies.data?.length ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div className="flex items-center gap-1.5">
              <CardTitle className="text-sm font-medium">Agent actions</CardTitle>
              <InfoHint text="Total autonomous agent actions recorded in the hash-chained ledger during the analysis run." />
            </div>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {agents.isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : agents.error ? (
              <span className="text-sm text-destructive">Error</span>
            ) : (
              <div className="text-2xl font-bold">{agents.data?.total_actions ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <div className="flex items-center gap-1.5">
              <CardTitle className="text-sm font-medium">Policy hash</CardTitle>
              <InfoHint text="Cryptographic SHA-256 hash of the policy definition used to judge truthfulness." />
            </div>
            <GitCommit className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {score.isLoading ? (
              <Skeleton className="h-8 w-28" />
            ) : score.error ? (
              <span className="text-sm text-destructive">Error</span>
            ) : (
              <div className="mono truncate text-xs">
                {score.data?.policy_hash ? `${score.data.policy_hash.slice(0, 16)}…` : "—"}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 3. Discrepancies & Score History Grid */}
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          {history.isLoading ? (
            <Skeleton className="h-64 rounded-xl" />
          ) : history.error ? (
            isNotFound(history.error) ? (
              <EmptyState
                icon={LineChart}
                title="No score history yet"
                description="Past score history will appear once multiple runs have been recorded."
              />
            ) : (
              <ErrorState
                title="Failed to load score history"
                error={history.error}
                retry={history.refetch}
              />
            )
          ) : (
            <ScoreSparkline history={history.data ?? []} />
          )}
        </div>

        <div>
          {discrepancies.isLoading ? (
            <Skeleton className="h-64 rounded-xl" />
          ) : discrepancies.error ? (
            isNotFound(discrepancies.error) ? (
              <EmptyState
                icon={AlertTriangle}
                title="No discrepancies detected"
                description="Your board is consistent with Git reality according to current policies."
              />
            ) : (
              <ErrorState
                title="Failed to load discrepancies"
                error={discrepancies.error}
                retry={discrepancies.refetch}
              />
            )
          ) : (
            <DiscrepancyInbox items={discrepancies.data ?? []} />
          )}
        </div>
      </div>

      {/* 4. Agent Activity Feed */}
      <div>
        {ledger.isLoading ? (
          <Skeleton className="h-48 rounded-xl" />
        ) : ledger.error ? (
          isNotFound(ledger.error) ? (
            <EmptyState
              icon={Activity}
              title="No ledger activity"
              description="Agent actions will be recorded here when an audit run executes."
            />
          ) : (
            <ErrorState
              title="Failed to load activity feed"
              error={ledger.error}
              retry={ledger.refetch}
            />
          )
        ) : (
          <AgentActivityFeed entries={ledger.data ?? []} limit={5} />
        )}
      </div>
    </div>
  )
}
