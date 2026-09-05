import { Loader2, Play, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useJobs } from "@/hooks/useJobs"

const COMMANDS = [
  {
    key: "audit",
    label: "Run audit",
    hint: "Diffs Jira tickets with Git commits & PRs",
  },
  {
    key: "score",
    label: "Run score",
    hint: "Recalculates truthfulness score from discrepancies",
  },
  {
    key: "report",
    label: "Run report",
    hint: "Regenerates standup summary and sprint plan",
  },
]

interface RunTriggerProps {
  variant?: "card" | "inline"
}

export function RunTrigger({ variant = "card" }: RunTriggerProps) {
  const { submit, status } = useJobs()
  const isRunning = status.data?.status === "pending" || status.data?.status === "running"

  if (variant === "inline") {
    return (
      <div className="flex flex-wrap items-center gap-2">
        {isRunning && (
          <div className="flex items-center gap-1.5 rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
            <span>{status.data?.command} running…</span>
          </div>
        )}
        {COMMANDS.map((cmd) => (
          <Button
            key={cmd.key}
            size="sm"
            variant="outline"
            disabled={isRunning}
            onClick={() => submit.mutate(cmd.key)}
            title={cmd.hint}
          >
            {isRunning && status.data?.command === cmd.key ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin text-primary" />
            ) : (
              <Play className="mr-1.5 h-3.5 w-3.5 text-primary" />
            )}
            {cmd.label}
          </Button>
        ))}
      </div>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <RefreshCw className="h-4 w-4 text-primary" />
          Re-run analysis
        </CardTitle>
        <CardDescription className="text-xs">
          Re-evaluates local artifacts and updates dashboard views without calling external APIs.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3">
          {COMMANDS.map((cmd) => (
            <button
              key={cmd.key}
              type="button"
              disabled={isRunning}
              onClick={() => submit.mutate(cmd.key)}
              className="flex flex-col items-start gap-1 rounded-md border p-3 text-left transition hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <div className="flex items-center gap-2 font-medium text-sm">
                {isRunning && status.data?.command === cmd.key ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                ) : (
                  <Play className="h-3.5 w-3.5 text-primary" />
                )}
                {cmd.label}
              </div>
              <span className="text-xs text-muted-foreground">{cmd.hint}</span>
            </button>
          ))}
        </div>
        {status.data && (
          <p className="pt-1 text-xs text-muted-foreground mono">
            {status.data.status === "completed"
              ? `✓ Completed ${status.data.result?.run_dir ?? status.data.command}`
              : status.data.status === "failed"
                ? `✗ Failed: ${status.data.error ?? "unknown error"}`
                : `${status.data.command} running…`}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
