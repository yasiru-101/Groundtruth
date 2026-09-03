import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { severityColor } from "@/score-band"
import type { DiscrepancyItem } from "@/types"

import { EvidenceDrawer } from "./EvidenceDrawer"

interface DiscrepancyInboxProps {
  items: DiscrepancyItem[]
  filter?: string
}

export function DiscrepancyInbox({ items, filter }: DiscrepancyInboxProps) {
  const [selected, setSelected] = useState<DiscrepancyItem | null>(null)
  const filtered = filter
    ? items.filter((d) => d.severity.toLowerCase() === filter.toLowerCase() || d.type.toLowerCase() === filter.toLowerCase())
    : items

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Discrepancies</CardTitle>
        <Badge variant="outline">{filtered.length}</Badge>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Severity</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Subject</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((item) => (
              <TableRow key={item.discrepancy_id}>
                <TableCell>
                  <span className={`rounded border px-2 py-0.5 text-xs ${severityColor(item.severity)}`}>
                    {item.severity}
                  </span>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{item.type}</TableCell>
                <TableCell className="max-w-xs truncate text-sm">{item.subject}</TableCell>
                <TableCell className="text-right">
                  <Button size="sm" variant="ghost" onClick={() => setSelected(item)}>
                    View
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-sm text-muted-foreground">
                  No discrepancies match the current filter.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        <EvidenceDrawer
          item={selected}
          open={Boolean(selected)}
          onOpenChange={(open) => !open && setSelected(null)}
        />
      </CardContent>
    </Card>
  )
}
