import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { LedgerEntry } from "@/types"

interface AgentActivityFeedProps {
  entries: LedgerEntry[]
  limit?: number
}

export function AgentActivityFeed({ entries, limit }: AgentActivityFeedProps) {
  const visible = limit ? entries.slice(0, limit) : entries
  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Time</TableHead>
            <TableHead>Actor</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Subject</TableHead>
            <TableHead>Outcome</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visible.map((entry) => (
            <TableRow key={entry.entry_id}>
              <TableCell className="mono text-xs text-muted-foreground">
                {new Date(entry.ts).toLocaleTimeString()}
              </TableCell>
              <TableCell className="capitalize">{entry.actor}</TableCell>
              <TableCell>{entry.action}</TableCell>
              <TableCell className="max-w-xs truncate">{entry.subject}</TableCell>
              <TableCell>
                <span
                  className={`rounded px-2 py-0.5 text-xs ${
                    entry.outcome === "ok"
                      ? "bg-emerald-500/10 text-emerald-500"
                      : entry.outcome === "refused"
                        ? "bg-rose-500/10 text-rose-500"
                        : "bg-secondary text-secondary-foreground"
                  }`}
                >
                  {entry.outcome}
                </span>
              </TableCell>
            </TableRow>
          ))}
          {visible.length === 0 && (
            <TableRow>
              <TableCell colSpan={5} className="text-center text-sm text-muted-foreground">
                No ledger entries.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  )
}
