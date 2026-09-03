import { Loader2, Play, RefreshCw } from "lucide-react"
import { useEffect } from "react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useJobs } from "@/hooks/useJobs"

const commands = [
  { key: "audit", label: "Re-run audit" },
  { key: "score", label: "Re-run score" },
  { key: "report", label: "Re-run report" },
]

export function RunTrigger() {
  const { submit, status, refreshAll } = useJobs()
  const isRunning = status.data?.status === "pending" || status.data?.status === "running"

  useEffect(() => {
    if (status.data?.status === "completed") {
      refreshAll()
    }
  }, [status.data?.status, refreshAll])

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          <RefreshCw className="h-4 w-4" />
          Live replay
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          {commands.map((cmd) => (
            <Button
              key={cmd.key}
              size="sm"
              variant="secondary"
              disabled={isRunning}
              onClick={() => submit.mutate(cmd.key)}
            >
              {isRunning && status.data?.command === cmd.key ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              {cmd.label}
            </Button>
          ))}
        </div>
        {status.data && (
          <p className="mt-3 text-xs text-muted-foreground mono">
            {status.data.status === "completed"
              ? `Completed ${status.data.result?.run_dir ?? ""}`
              : status.data.status === "failed"
                ? `Failed: ${status.data.error ?? "unknown"}`
                : `${status.data.command} running…`}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
