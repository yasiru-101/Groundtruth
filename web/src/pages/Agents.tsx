import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AgentActivityFeed } from "@/components/agents/AgentActivityFeed"
import { AgentCard } from "@/components/agents/AgentCard"
import { RunTrigger } from "@/components/agents/RunTrigger"
import { DeliveryTimeline } from "@/components/delivery/DeliveryTimeline"
import { TraceabilityMatrix } from "@/components/trace/TraceabilityMatrix"
import { useAgentsSummary } from "@/hooks/useAgents"
import { useDelivery, useTrace } from "@/hooks/useBoard"
import { useLedger } from "@/hooks/useLedger"

export function Agents() {
  const agents = useAgentsSummary()
  const ledger = useLedger()
  const delivery = useDelivery()
  const trace = useTrace()

  if (agents.isLoading || ledger.isLoading) {
    return <div className="p-8 text-center text-muted-foreground">Loading agents…</div>
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {agents.data?.actors.map((actor) => <AgentCard key={actor.actor} activity={actor} />)}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <RunTrigger />
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Agent summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-muted-foreground text-sm">Total actions</p>
                <p className="text-2xl font-bold">{agents.data?.total_actions ?? 0}</p>
              </div>
              <div>
                <p className="text-muted-foreground text-sm">Refusals</p>
                <p className="text-2xl font-bold">{agents.data?.refusals ?? 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <DeliveryTimeline delivery={delivery.data} />
        <TraceabilityMatrix trace={trace.data} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ledger-backed activity</CardTitle>
        </CardHeader>
        <CardContent>
          <AgentActivityFeed entries={ledger.data ?? []} />
        </CardContent>
      </Card>
    </div>
  )
}
