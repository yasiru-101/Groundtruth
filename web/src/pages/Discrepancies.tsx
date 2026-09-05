import { useState } from "react"
import { AlertTriangle } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/common/EmptyState"
import { ErrorState } from "@/components/common/ErrorState"
import { PageHeader } from "@/components/layout/PageHeader"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { EvidenceDrawer } from "@/components/discrepancies/EvidenceDrawer"
import { useDiscrepancies } from "@/hooks/useDiscrepancies"
import { isNotFound } from "@/lib/query"
import { severityColor } from "@/score-band"
import type { DiscrepancyItem } from "@/types"

const SEVERITIES = ["all", "high", "medium", "low"]
const TYPES = ["all", "missing_pr", "stale", "unverified_done", "duplicate"]

export function Discrepancies() {
  const [severity, setSeverity] = useState<string>("all")
  const [type, setType] = useState<string>("all")
  const [selected, setSelected] = useState<DiscrepancyItem | null>(null)

  const { data, isLoading, error, refetch } = useDiscrepancies({
    severity: severity === "all" ? undefined : severity,
    type: type === "all" ? undefined : type,
  })

  return (
    <div className="space-y-6">
      <PageHeader
        title="Discrepancies"
        description="Gaps Groundtruth found between Jira and Git, each backed by evidence."
      />
      <div className="flex flex-wrap items-center gap-2">
        {SEVERITIES.map((s) => (
          <Button
            key={s}
            size="sm"
            variant={severity === s ? "default" : "outline"}
            onClick={() => setSeverity(s)}
          >
            {s}
          </Button>
        ))}
        <span className="mx-2 h-4 w-px bg-border" />
        {TYPES.map((t) => (
          <Button
            key={t}
            size="sm"
            variant={type === t ? "secondary" : "outline"}
            onClick={() => setType(t)}
          >
            {t}
          </Button>
        ))}
        <Badge variant="outline" className="ml-auto">
          {data?.length ?? 0}
        </Badge>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : error ? (
        isNotFound(error) ? (
          <EmptyState
            icon={AlertTriangle}
            title="No discrepancies found"
            description="No discrepancies recorded for this snapshot."
          />
        ) : (
          <ErrorState
            title="Failed to load discrepancies"
            error={error}
            retry={refetch}
          />
        )
      ) : data?.length === 0 ? (
        <EmptyState
          icon={AlertTriangle}
          title="No matching discrepancies"
          description={
            severity !== "all" || type !== "all"
              ? "No discrepancies match the active filters."
              : "No discrepancies found between Git and Jira."
          }
          actionLabel={severity !== "all" || type !== "all" ? "Reset filters" : undefined}
          onAction={
            severity !== "all" || type !== "all"
              ? () => {
                  setSeverity("all")
                  setType("all")
                }
              : undefined
          }
        />
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Severity</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Subject</TableHead>
                <TableHead>Detected</TableHead>
                <TableHead className="text-right">Evidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data?.map((item) => (
                <TableRow key={item.discrepancy_id}>
                  <TableCell>
                    <span className={`rounded border px-2 py-0.5 text-xs ${severityColor(item.severity)}`}>
                      {item.severity}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{item.type}</TableCell>
                  <TableCell className="max-w-xs truncate">{item.subject}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {item.detected_at ? new Date(item.detected_at).toLocaleDateString() : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button size="sm" variant="ghost" onClick={() => setSelected(item)}>
                      View
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <EvidenceDrawer
        item={selected}
        open={Boolean(selected)}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </div>
  )
}
