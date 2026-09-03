import { useQuery } from "@tanstack/react-query"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PlanTable } from "@/components/sprint/PlanTable"
import { api } from "@/lib/api"
import { usePlan } from "@/hooks/useBoard"

export function Report() {
  const report = useQuery({
    queryKey: ["report"],
    queryFn: api.report,
  })
  const plan = usePlan()

  if (report.isLoading) return <div className="p-8 text-center text-muted-foreground">Loading report…</div>

  return (
    <div className="space-y-4">
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Active tickets</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{report.data?.active_tickets ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Open discrepancies</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{report.data?.open_discrepancies ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Unverified items</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{report.data?.unverified_items ?? 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Stale items</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{report.data?.stale_items ?? 0}</div>
          </CardContent>
        </Card>
      </div>

      <PlanTable plan={plan.data} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Standup report</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="prose prose-invert max-w-none">
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
              {report.data?.prose}
            </pre>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
