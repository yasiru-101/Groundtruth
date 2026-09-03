import { Link2 } from "lucide-react"

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { TraceabilityMatrix as TraceabilityMatrixType } from "@/types"

interface TraceabilityMatrixProps {
  trace: TraceabilityMatrixType | undefined
}

export function TraceabilityMatrix({ trace }: TraceabilityMatrixProps) {
  if (!trace) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Traceability matrix</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No traceability data available.</p>
        </CardContent>
      </Card>
    )
  }

  const outcomes = (trace.snapshot.outcomes ?? {}) as Record<string, string>

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <Link2 className="h-4 w-4" />
          Traceability matrix
        </CardTitle>
        <span className="text-xs text-muted-foreground">
          {trace.bindings.length} binding{trace.bindings.length === 1 ? "" : "s"}
        </span>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Acceptance criteria</TableHead>
              <TableHead>Test</TableHead>
              <TableHead>Bound by</TableHead>
              <TableHead>Outcome</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {trace.bindings.map((binding) => {
              const outcome = outcomes[binding.test_node_id] ?? "unknown"
              return (
                <TableRow key={`${binding.ac_id}-${binding.test_node_id}`}>
                  <TableCell className="mono text-xs">{binding.ac_id}</TableCell>
                  <TableCell className="mono text-xs">{binding.test_node_id}</TableCell>
                  <TableCell className="capitalize text-xs">{binding.bound_by}</TableCell>
                  <TableCell>
                    <span
                      className={`rounded px-2 py-0.5 text-xs ${
                        outcome === "passed"
                          ? "bg-emerald-500/10 text-emerald-500"
                          : outcome === "failed"
                            ? "bg-rose-500/10 text-rose-500"
                            : "bg-secondary text-secondary-foreground"
                      }`}
                    >
                      {outcome}
                    </span>
                  </TableCell>
                </TableRow>
              )
            })}
            {trace.bindings.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-sm text-muted-foreground">
                  No bindings found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
