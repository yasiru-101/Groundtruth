import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { ScoreDimension } from "@/types"

import { scoreColorClass } from "@/score-band"

interface DimensionBreakdownProps {
  dimensions: ScoreDimension[]
}

export function DimensionBreakdown({ dimensions }: DimensionBreakdownProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Dimension breakdown</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {dimensions.map((d) => (
          <div key={d.name} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="font-medium capitalize">{d.name.replace(/_/g, " ")}</span>
              <span className={`font-bold tabular-nums ${scoreColorClass(d.value ?? 0)}`}>
                {d.value === null ? "—" : `${Math.round(d.value * 100)}%`}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${scoreColorClass(d.value ?? 0).replace("text-", "bg-")}`}
                style={{ width: `${Math.round((d.value ?? 0) * 100)}%` }}
              />
            </div>
            <p className="text-xs text-muted-foreground">weight {(d.weight * 100).toFixed(0)}%</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
