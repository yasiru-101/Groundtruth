import { useQuery } from "@tanstack/react-query"
import { FileText } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/common/EmptyState"
import { ErrorState } from "@/components/common/ErrorState"
import { PageHeader } from "@/components/layout/PageHeader"
import { PlanTable } from "@/components/sprint/PlanTable"
import { api } from "@/lib/api"
import { usePlan } from "@/hooks/useBoard"
import { isNotFound } from "@/lib/query"

export function Report() {
  const report = useQuery({
    queryKey: ["report"],
    queryFn: api.report,
  })
  const plan = usePlan()

  return (
    <div className="space-y-6">
      <PageHeader
        title="Report"
        description="Standup summary and sprint plan drawn from the latest run."
      />

      {/* Metrics Row */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Active tickets</CardTitle>
          </CardHeader>
          <CardContent>
            {report.isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : report.error ? (
              <span className="text-sm text-destructive">—</span>
            ) : (
              <div className="text-2xl font-bold">{report.data?.active_tickets ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Open discrepancies</CardTitle>
          </CardHeader>
          <CardContent>
            {report.isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : report.error ? (
              <span className="text-sm text-destructive">—</span>
            ) : (
              <div className="text-2xl font-bold">{report.data?.open_discrepancies ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Unverified items</CardTitle>
          </CardHeader>
          <CardContent>
            {report.isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : report.error ? (
              <span className="text-sm text-destructive">—</span>
            ) : (
              <div className="text-2xl font-bold">{report.data?.unverified_items ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Stale items</CardTitle>
          </CardHeader>
          <CardContent>
            {report.isLoading ? (
              <Skeleton className="h-8 w-16" />
            ) : report.error ? (
              <span className="text-sm text-destructive">—</span>
            ) : (
              <div className="text-2xl font-bold">{report.data?.stale_items ?? 0}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Plan Table */}
      {plan.isLoading ? (
        <Skeleton className="h-64 rounded-xl" />
      ) : plan.error ? (
        <ErrorState title="Failed to load sprint plan" error={plan.error} retry={plan.refetch} />
      ) : (
        <PlanTable plan={plan.data} />
      )}

      {/* Standup prose card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Standup report</CardTitle>
        </CardHeader>
        <CardContent>
          {report.isLoading ? (
            <div className="space-y-2 py-4">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-4/6" />
            </div>
          ) : report.error ? (
            isNotFound(report.error) ? (
              <EmptyState
                icon={FileText}
                title="No report generated yet"
                description="Run report analysis to generate a standup summary."
              />
            ) : (
              <ErrorState
                title="Failed to load report"
                error={report.error}
                retry={report.refetch}
              />
            )
          ) : (
            <div className="prose prose-invert max-w-none">
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
                {report.data?.prose || "No standup prose generated."}
              </pre>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
