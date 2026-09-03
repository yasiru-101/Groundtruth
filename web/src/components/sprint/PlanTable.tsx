import { AlertTriangle, Calendar } from "lucide-react"

import { Badge } from "@/components/ui/badge"
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
import type { SprintPlan } from "@/types"

interface PlanTableProps {
  plan: SprintPlan | undefined
}

export function PlanTable({ plan }: PlanTableProps) {
  if (!plan) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sprint plan</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No sprint plan available.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base flex items-center gap-2">
          <Calendar className="h-4 w-4" />
          Sprint plan
        </CardTitle>
        {plan.over_committed && (
          <Badge variant="destructive" className="flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" />
            Over committed
          </Badge>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div className="rounded-md border p-3">
            <p className="text-muted-foreground">Velocity</p>
            <p className="text-xl font-bold">{plan.velocity}</p>
          </div>
          <div className="rounded-md border p-3">
            <p className="text-muted-foreground">Capacity</p>
            <p className="text-xl font-bold">{plan.capacity}</p>
          </div>
          <div className="rounded-md border p-3">
            <p className="text-muted-foreground">Selected</p>
            <p className="text-xl font-bold">{plan.total_selected_points} pts</p>
          </div>
        </div>

        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Ticket</TableHead>
              <TableHead>Summary</TableHead>
              <TableHead>Points</TableHead>
              <TableHead>Assignee</TableHead>
              <TableHead>Depends on</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {plan.selected.map((ticket) => (
              <TableRow key={ticket.key}>
                <TableCell className="mono text-xs font-medium">{ticket.key}</TableCell>
                <TableCell className="text-sm">{ticket.summary}</TableCell>
                <TableCell>{ticket.points}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {ticket.assignee ?? "—"}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {ticket.depends_on.length > 0 ? ticket.depends_on.join(", ") : "—"}
                </TableCell>
              </TableRow>
            ))}
            {plan.selected.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                  No tickets selected.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>

        {plan.unscheduled.length > 0 && (
          <div>
            <h4 className="mb-2 text-sm font-medium text-muted-foreground">Unscheduled</h4>
            <div className="space-y-2">
              {plan.unscheduled.map((ticket) => (
                <div
                  key={ticket.key}
                  className="flex items-center justify-between rounded-md border p-2 text-sm"
                >
                  <span className="mono text-xs font-medium">{ticket.key}</span>
                  <span>{ticket.summary}</span>
                  <span className="text-muted-foreground">{ticket.points} pts</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
