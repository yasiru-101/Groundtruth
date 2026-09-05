import { Link } from "react-router-dom"
import { AlertTriangle, Info } from "lucide-react"

import { useSystemStatus } from "@/hooks/useSystemStatus"

export function DemoBanner() {
  const { demoMode, connectedCount, artifactsDir, isLoading, isOffline } = useSystemStatus()

  if (isOffline) {
    return (
      <div className="flex items-center gap-2 border-b bg-destructive/15 px-4 py-2 text-xs text-destructive">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span className="font-semibold">Backend server offline:</span>
        <span className="hidden sm:inline">
          Cannot connect to Groundtruth API at <code>http://localhost:8000</code>. Please start the backend in a terminal with:
        </span>
        <code className="rounded bg-background px-1.5 py-0.5 font-mono text-[11px] text-foreground">
          python -m groundtruth.api
        </code>
      </div>
    )
  }

  if (isLoading) return null

  if (!demoMode) {
    return (
      <div className="flex items-center gap-2 border-b bg-emerald-500/10 px-4 py-2 text-xs text-emerald-600">
        <Info className="h-4 w-4 shrink-0" />
        <span className="font-medium">Live mode</span>
        <span className="hidden text-muted-foreground sm:inline">
          Reading artifacts from {artifactsDir || "project artifacts directory"}.
        </span>
      </div>
    )
  }

  if (connectedCount > 0) {
    return (
      <div className="flex items-center gap-2 border-b bg-amber-500/10 px-4 py-2 text-xs text-amber-600">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span className="font-medium">Connected, but still viewing demo data</span>
        <span className="hidden text-muted-foreground sm:inline">
          The dashboard is reading the bundled demo snapshot. To collect fresh live data, run
          <code className="mx-1 rounded bg-background px-1 py-0.5">groundtruth --run-mode live audit</code>
          from the CLI, then refresh.
        </span>
        <Link to="/settings" className="ml-auto font-medium underline">
          Settings
        </Link>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2 border-b bg-muted/50 px-4 py-2 text-xs text-muted-foreground">
      <Info className="h-4 w-4 shrink-0" />
      <span className="font-medium">Showing demo data.</span>
      <span className="hidden sm:inline">
        Connect GitHub and Jira in Settings to analyze your own board.
      </span>
      <Link to="/settings" className="ml-auto font-medium underline">
        Settings
      </Link>
    </div>
  )
}
