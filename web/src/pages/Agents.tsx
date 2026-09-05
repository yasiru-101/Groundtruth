import { Activity } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/common/EmptyState"
import { ErrorState } from "@/components/common/ErrorState"
import { PageHeader } from "@/components/layout/PageHeader"
import { InfoHint } from "@/components/ui/info-hint"
import { AgentActivityFeed } from "@/components/agents/AgentActivityFeed"
import { AgentCard } from "@/components/agents/AgentCard"
import { RunTrigger } from "@/components/agents/RunTrigger"
import { DeliveryTimeline } from "@/components/delivery/DeliveryTimeline"
import { TraceabilityMatrix } from "@/components/trace/TraceabilityMatrix"
import { useAgentsSummary } from "@/hooks/useAgents"
import { useDelivery, useTrace } from "@/hooks/useBoard"
import { useLedger } from "@/hooks/useLedger"
import { isNotFound } from "@/lib/query"

export function Agents() {
  const agents = useAgentsSummary()
  const ledger = useLedger()
  const delivery = useDelivery()
  const trace = useTrace()

  return (
    <div className="space-y-6">
      <PageHeader
        title="Agents"
        description="What each autonomous agent did and the ledger it wrote."
      />

      {/* Agent actor cards */}
      {agents.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Skeleton className="h-32 rounded-xl" />
          <Skeleton className="h-32 rounded-xl" />
          <Skeleton className="h-32 rounded-xl" />
          <Skeleton className="h-32 rounded-xl" />
        </div>
      ) : agents.error ? (
        isNotFound(agents.error) ? (
          <EmptyState
            icon={Activity}
            title="No agents found"
            description="Agent summary is not available for this snapshot."
          />
        ) : (
          <ErrorState title="Failed to load agent summary" error={agents.error} retry={agents.refetch} />
        )
      ) : agents.data?.actors.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No active agents"
          description="No autonomous agent actions have been recorded yet."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {agents.data?.actors.map((actor) => <AgentCard key={actor.actor} activity={actor} />)}
        </div>
      )}

      {/* Trigger & Summary */}
      <div className="grid gap-4 md:grid-cols-2">
        <RunTrigger variant="card" />
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Agent summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-muted-foreground text-sm">Total actions</p>
                {agents.isLoading ? (
                  <Skeleton className="mt-1 h-8 w-16" />
                ) : (
                  <p className="text-2xl font-bold">{agents.data?.total_actions ?? 0}</p>
                )}
              </div>
              <div>
                <p className="flex items-center gap-1 text-muted-foreground text-sm">
                  <span>Refusals</span>
                  <InfoHint text="Actions proposed by agents that were blocked by governance policies or verification checks." />
                </p>
                {agents.isLoading ? (
                  <Skeleton className="mt-1 h-8 w-16" />
                ) : (
                  <p className="text-2xl font-bold">{agents.data?.refusals ?? 0}</p>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Delivery & Trace */}
      <div className="grid gap-4 md:grid-cols-2">
        {delivery.isLoading ? (
          <Skeleton className="h-64 rounded-xl" />
        ) : delivery.error ? (
          <ErrorState title="Failed to load delivery timeline" error={delivery.error} retry={delivery.refetch} />
        ) : (
          <DeliveryTimeline delivery={delivery.data} />
        )}

        {trace.isLoading ? (
          <Skeleton className="h-64 rounded-xl" />
        ) : trace.error ? (
          <ErrorState title="Failed to load traceability matrix" error={trace.error} retry={trace.refetch} />
        ) : (
          <TraceabilityMatrix trace={trace.data} />
        )}
      </div>

      {/* Activity Feed */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ledger-backed activity</CardTitle>
        </CardHeader>
        <CardContent>
          {ledger.isLoading ? (
            <Skeleton className="h-48 rounded-xl" />
          ) : ledger.error ? (
            isNotFound(ledger.error) ? (
              <EmptyState
                icon={Activity}
                title="No ledger activity"
                description="Agent activity will appear here after analysis runs."
              />
            ) : (
              <ErrorState title="Failed to load ledger" error={ledger.error} retry={ledger.refetch} />
            )
          ) : (
            <AgentActivityFeed entries={ledger.data ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
