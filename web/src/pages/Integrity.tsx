import { useQuery } from "@tanstack/react-query"
import { CheckCircle, XCircle } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { ChainStrip } from "@/components/integrity/ChainStrip"
import { api } from "@/lib/api"

export function Integrity() {
  const integrity = useQuery({
    queryKey: ["ledger", "integrity"],
    queryFn: api.ledgerIntegrity,
  })
  const ledger = useQuery({
    queryKey: ["ledger"],
    queryFn: api.ledger,
  })

  if (integrity.isLoading || ledger.isLoading) {
    return <div className="p-8 text-center text-muted-foreground">Loading integrity…</div>
  }

  const allValid = integrity.data?.every((i) => i.valid) ?? false
  const refusals = ledger.data?.filter((e) => e.outcome === "refused") ?? []

  return (
    <div className="space-y-6">
      <Card className={allValid ? "border-emerald-500/30" : "border-rose-500/30"}>
        <CardHeader className="flex flex-row items-center gap-3">
          {allValid ? (
            <CheckCircle className="h-6 w-6 text-emerald-500" />
          ) : (
            <XCircle className="h-6 w-6 text-rose-500" />
          )}
          <div>
            <CardTitle className="text-base">Ledger integrity</CardTitle>
            <p className="text-sm text-muted-foreground">
              {allValid
                ? "All ledger hash chains verified."
                : "One or more ledgers failed verification."}
            </p>
          </div>
        </CardHeader>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Verification results</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Run</TableHead>
                  <TableHead>Entries</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {integrity.data?.map((item) => (
                  <TableRow key={item.run_dir}>
                    <TableCell className="mono text-xs">{item.run_dir}</TableCell>
                    <TableCell>{item.entries}</TableCell>
                    <TableCell>
                      {item.valid ? (
                        <span className="rounded bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-500">
                          verified
                        </span>
                      ) : (
                        <span className="rounded bg-rose-500/10 px-2 py-0.5 text-xs text-rose-500">
                          broken
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <ChainStrip integrity={integrity.data} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Refusals</CardTitle>
        </CardHeader>
        <CardContent>
          {refusals.length === 0 ? (
            <p className="text-sm text-muted-foreground">No refused actions.</p>
          ) : (
            <ul className="space-y-2">
              {refusals.map((entry) => (
                <li key={entry.entry_id} className="rounded-md border p-3 text-sm">
                  <span className="font-medium">{entry.actor}</span>{" "}
                  <span className="text-muted-foreground">{entry.action}</span>{" "}
                  <span className="text-rose-500">refused</span>
                  {entry.error && (
                    <p className="mt-1 text-xs text-muted-foreground">{entry.error}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
