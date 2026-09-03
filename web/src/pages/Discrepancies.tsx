import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { severityColor } from "@/score-band"
import type { DiscrepancyItem } from "@/types"

const SEVERITIES = ["all", "high", "medium", "low"]
const TYPES = ["all", "missing_pr", "stale", "unverified_done", "duplicate"]

export function Discrepancies() {
  const [severity, setSeverity] = useState<string>("all")
  const [type, setType] = useState<string>("all")
  const [selected, setSelected] = useState<DiscrepancyItem | null>(null)

  const { data, isLoading } = useDiscrepancies({
    severity: severity === "all" ? undefined : severity,
    type: type === "all" ? undefined : type,
  })

  if (isLoading) return <div className="p-8 text-center text-muted-foreground">Loading…</div>

  return (
    <div className="space-y-4">
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

      <EvidenceDrawer
        item={selected}
        open={Boolean(selected)}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </div>
  )
}
