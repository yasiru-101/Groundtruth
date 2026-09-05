import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { GitCompare } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/common/EmptyState"
import { ErrorState } from "@/components/common/ErrorState"
import { PageHeader } from "@/components/layout/PageHeader"
import { InfoHint } from "@/components/ui/info-hint"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useRuns } from "@/hooks/useRuns"
import { api } from "@/lib/api"
import { isNotFound } from "@/lib/query"
import { scoreColorClass } from "@/score-band"
import type { ScoreComparison } from "@/types"

const RUN_LABEL_DESCRIPTIONS: Record<string, string> = {
  audit: "Scans Git commits and PRs against Jira tickets to find discrepancies.",
  score: "Evaluates active policy dimensions to calculate the truthfulness score.",
  report: "Generates the standup summary and sprint delivery plan.",
}

export function Runs() {
  const runs = useRuns()
  const [before, setBefore] = useState<string>("")
  const [after, setAfter] = useState<string>("")

  const scoreRuns = runs.data?.filter((r) => r.label === "score") ?? []

  const comparison = useQuery<ScoreComparison>({
    queryKey: ["score", "compare", before, after],
    queryFn: () => api.compareScore(before, after),
    enabled: Boolean(before) && Boolean(after) && before !== after,
  })

  return (
    <div className="space-y-6">
      <PageHeader
        title="Runs"
        description="Browse past runs and compare truthfulness scores over time."
      />

      {runs.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : runs.error ? (
        isNotFound(runs.error) ? (
          <EmptyState
            icon={GitCompare}
            title="No past runs found"
            description="Artifact runs will appear here after executing an audit, score, or report."
          />
        ) : (
          <ErrorState
            title="Failed to load runs"
            error={runs.error}
            retry={runs.refetch}
          />
        )
      ) : runs.data?.length === 0 ? (
        <EmptyState
          icon={GitCompare}
          title="No past runs found"
          description="Artifact runs will appear here after executing an audit, score, or report."
        />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run directory</TableHead>
                <TableHead>
                  <div className="flex items-center gap-1">
                    <span>Label</span>
                    <InfoHint text="The command that created this artifact: audit, score, or report." />
                  </div>
                </TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Files</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data?.map((run) => (
                <TableRow key={run.run_id}>
                  <TableCell className="mono text-xs">{run.run_dir}</TableCell>
                  <TableCell>
                    <span
                      className="cursor-help rounded bg-secondary px-2 py-0.5 text-xs font-medium"
                      title={RUN_LABEL_DESCRIPTIONS[run.label] ?? run.label}
                    >
                      {run.label}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {new Date(run.created_at).toLocaleString()}
                  </TableCell>
                  <TableCell>{run.files.length}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Compare score runs</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-4 sm:flex-row">
            <div className="flex-1 space-y-2">
              <label className="text-sm text-muted-foreground" htmlFor="before">Before</label>
              <select
                id="before"
                value={before}
                onChange={(e) => setBefore(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value="">Select a score run</option>
                {scoreRuns.map((run) => (
                  <option key={run.run_dir} value={run.run_dir}>
                    {run.run_dir}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1 space-y-2">
              <label className="text-sm text-muted-foreground" htmlFor="after">After</label>
              <select
                id="after"
                value={after}
                onChange={(e) => setAfter(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value="">Select a score run</option>
                {scoreRuns.map((run) => (
                  <option key={run.run_dir} value={run.run_dir}>
                    {run.run_dir}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {scoreRuns.length < 2 && (
            <p className="text-sm text-muted-foreground">
              At least two score runs are required to compare.
            </p>
          )}

          {comparison.isLoading && (
            <p className="text-sm text-muted-foreground">Loading comparison…</p>
          )}

          {comparison.error && (
            <p className="text-sm text-rose-500">Failed to load comparison.</p>
          )}

          {comparison.data && (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="rounded-md border p-3 text-center">
                  <p className="text-xs text-muted-foreground">Before</p>
                  <p className="text-xl font-bold">
                    {Math.round(comparison.data.before.total * 100)}
                  </p>
                  <p className="mono text-xs text-muted-foreground truncate">
                    {comparison.data.before.run_dir}
                  </p>
                </div>
                <div className="rounded-md border p-3 text-center">
                  <p className="text-xs text-muted-foreground">Delta</p>
                  <p
                    className={`text-xl font-bold ${scoreColorClass(
                      0.5 + comparison.data.delta
                    )}`}
                  >
                    {comparison.data.delta > 0 ? "+" : ""}
                    {Math.round(comparison.data.delta * 100)}
                  </p>
                </div>
                <div className="rounded-md border p-3 text-center">
                  <p className="text-xs text-muted-foreground">After</p>
                  <p className="text-xl font-bold">
                    {Math.round(comparison.data.after.total * 100)}
                  </p>
                  <p className="mono text-xs text-muted-foreground truncate">
                    {comparison.data.after.run_dir}
                  </p>
                </div>
              </div>

              {comparison.data.dimensions_changed.length > 0 && (
                <div>
                  <h4 className="mb-2 text-sm font-medium">Dimensions changed</h4>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Dimension</TableHead>
                        <TableHead>Before</TableHead>
                        <TableHead>After</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {comparison.data.dimensions_changed.map((dim) => (
                        <TableRow key={dim.name}>
                          <TableCell className="text-sm">{dim.name}</TableCell>
                          <TableCell>
                            {dim.before !== null ? Math.round(dim.before * 100) : "—"}
                          </TableCell>
                          <TableCell>
                            {dim.after !== null ? Math.round(dim.after * 100) : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <h4 className="mb-2 text-sm font-medium">Resolved</h4>
                  {comparison.data.resolved.length === 0 ? (
                    <p className="text-sm text-muted-foreground">None</p>
                  ) : (
                    <ul className="space-y-1">
                      {comparison.data.resolved.map((id) => (
                        <li key={id} className="mono text-xs">
                          {id}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div>
                  <h4 className="mb-2 text-sm font-medium">Introduced</h4>
                  {comparison.data.introduced.length === 0 ? (
                    <p className="text-sm text-muted-foreground">None</p>
                  ) : (
                    <ul className="space-y-1">
                      {comparison.data.introduced.map((id) => (
                        <li key={id} className="mono text-xs">
                          {id}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
