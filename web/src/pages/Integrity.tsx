import { useQuery } from "@tanstack/react-query"
import { CheckCircle, ShieldCheck, XCircle } from "lucide-react"

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
import { ChainStrip } from "@/components/integrity/ChainStrip"
import { api } from "@/lib/api"
import { isNotFound } from "@/lib/query"

export function Integrity() {
  const integrity = useQuery({
    queryKey: ["ledger", "integrity"],
    queryFn: api.ledgerIntegrity,
  })
  const ledger = useQuery({
    queryKey: ["ledger"],
    queryFn: api.ledger,
  })

  const isLoading = integrity.isLoading || ledger.isLoading
  const allValid = integrity.data?.every((i) => i.valid) ?? false
  const refusals = ledger.data?.filter((e) => e.outcome === "refused") ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        title="Integrity"
        description="Verify that the hash-chained ledger was not tampered with."
      />

      {/* Top Banner Status */}
      {isLoading ? (
        <Skeleton className="h-20 rounded-xl" />
      ) : integrity.error ? (
        <ErrorState
          title="Failed to check integrity"
          error={integrity.error}
          retry={integrity.refetch}
        />
      ) : !integrity.data || integrity.data.length === 0 ? (
        <EmptyState
          icon={ShieldCheck}
          title="No ledger files to verify"
          description="Ledger integrity checks will run after agent audit actions are recorded."
        />
      ) : (
        <Card className={allValid ? "border-emerald-500/30" : "border-rose-500/30"}>
          <CardHeader className="flex flex-row items-center gap-3">
            {allValid ? (
              <CheckCircle className="h-6 w-6 text-emerald-500" />
            ) : (
              <XCircle className="h-6 w-6 text-rose-500" />
            )}
            <div>
              <div className="flex items-center gap-2">
                <CardTitle className="text-base">Ledger integrity</CardTitle>
                <InfoHint text="Every action written to the ledger is linked to the previous entry by cryptographic SHA-256 hash. Any retroactive change invalidates the entire chain." />
              </div>
              <p className="text-sm text-muted-foreground">
                {allValid
                  ? "All ledger hash chains verified."
                  : "One or more ledgers failed verification."}
              </p>
            </div>
          </CardHeader>
        </Card>
      )}

      {/* Verification Table & Visual Chain Strip */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Verification results</CardTitle>
          </CardHeader>
          <CardContent>
            {integrity.isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : integrity.error ? (
              <p className="text-sm text-destructive">Could not load verification results.</p>
            ) : !integrity.data || integrity.data.length === 0 ? (
              <p className="text-sm text-muted-foreground">No verification records found.</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Run</TableHead>
                    <TableHead>Entries</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {integrity.data.map((item) => (
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
            )}
          </CardContent>
        </Card>

        {integrity.isLoading ? (
          <Skeleton className="h-64 rounded-xl" />
        ) : (
          <ChainStrip integrity={integrity.data} />
        )}
      </div>

      {/* Refusals Section */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <CardTitle className="text-base">Refusals</CardTitle>
            <InfoHint text="Actions submitted to the agent runner that were rejected by policy or boundary checks." />
          </div>
        </CardHeader>
        <CardContent>
          {ledger.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : ledger.error ? (
            isNotFound(ledger.error) ? (
              <p className="text-sm text-muted-foreground">No ledger found.</p>
            ) : (
              <p className="text-sm text-destructive">Could not load refusals.</p>
            )
          ) : refusals.length === 0 ? (
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
