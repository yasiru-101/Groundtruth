import { CheckCircle2, GitPullRequest, XCircle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { DeliveryItem } from "@/types"

interface DeliveryTimelineProps {
  delivery: DeliveryItem | undefined
}

export function DeliveryTimeline({ delivery }: DeliveryTimelineProps) {
  if (!delivery) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Delivery timeline</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No delivery run available.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <GitPullRequest className="h-4 w-4" />
          Delivery timeline
        </CardTitle>
        <Badge variant={delivery.green ? "default" : "destructive"}>
          {delivery.green ? "green" : "red"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Ticket</span>
          <span className="font-medium mono">{delivery.ticket_key}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Branch</span>
          <span className="font-medium mono">{delivery.branch}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Phase</span>
          <span className="font-medium capitalize">{delivery.phase}</span>
        </div>
        {delivery.head_sha && (
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Head</span>
            <span className="mono text-xs">{delivery.head_sha.slice(0, 12)}</span>
          </div>
        )}

        <div className="relative border-l border-border pl-4 space-y-4">
          {delivery.iterations.map((iteration, idx) => {
            const iter = iteration as Record<string, unknown>
            const green = Boolean(iter.green)
            const redGate = Boolean(iter.red_gate_valid)
            return (
              <div key={idx} className="relative">
                <span
                  className={`absolute -left-[calc(1rem+5px)] top-1 h-2.5 w-2.5 rounded-full border-2 ${
                    green ? "bg-emerald-500 border-emerald-500" : "bg-rose-500 border-rose-500"
                  }`}
                />
                <div className="flex items-center gap-2 text-sm">
                  {green ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  ) : (
                    <XCircle className="h-4 w-4 text-rose-500" />
                  )}
                  <span className="font-medium capitalize">{String(iter.phase)}</span>
                  <span className="text-xs text-muted-foreground">
                    red gate {redGate ? "passed" : "failed"}
                  </span>
                </div>
                {Array.isArray(iter.files_changed) && (iter.files_changed as string[]).length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground mono">
                    {(iter.files_changed as string[]).join(", ")}
                  </p>
                )}
                {Array.isArray(iter.notes) && (iter.notes as string[]).map((note, nidx) => (
                  <p key={nidx} className="mt-1 text-xs text-muted-foreground">
                    {note}
                  </p>
                ))}
              </div>
            )
          })}
        </div>

        {delivery.refusals.length > 0 && (
          <div className="rounded-md border border-rose-500/20 bg-rose-500/10 p-3 text-xs text-rose-500">
            {delivery.refusals.length} refusal{delivery.refusals.length === 1 ? "" : "s"}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
