import { AlertTriangle, CheckCircle2 } from "lucide-react"

import { InfoHint } from "@/components/ui/info-hint"
import { scoreBand } from "@/score-band"
import type { DiscrepancyItem } from "@/types"

interface ScoreVerdictProps {
  total: number
  discrepancies?: DiscrepancyItem[]
}

export function ScoreVerdict({ total, discrepancies = [] }: ScoreVerdictProps) {
  const band = scoreBand(total)
  const high = discrepancies.filter((d) => d.severity === "high").length
  const open = discrepancies.length

  return (
    <div className="space-y-1">
      <p className="text-sm font-medium text-foreground">
        {total === 0 && open === 0 ? (
          <span className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            No score computed yet.
          </span>
        ) : (
          <span className="flex items-center gap-2">
            {band === "high" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
            ) : (
              <AlertTriangle className="h-4 w-4 text-score-mid" />
            )}
            This board is {Math.round(total * 100)}% truthful.
          </span>
        )}
        <InfoHint text="A weighted 0-100 measure of how well the Jira board matches Git reality. Missing dimensions are excluded, not scored as perfect." />
      </p>
      {open > 0 && (
        <p className="text-sm text-muted-foreground">
          {open} open discrepancy{open === 1 ? "" : "s"}
          {high > 0 ? `, ${high} high severity` : ""}.
        </p>
      )}
    </div>
  )
}
