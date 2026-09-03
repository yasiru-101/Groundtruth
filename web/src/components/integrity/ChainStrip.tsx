import { Link } from "lucide-react"

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { LedgerIntegrity } from "@/types"

interface ChainStripProps {
  integrity: LedgerIntegrity[] | undefined
}

export function ChainStrip({ integrity }: ChainStripProps) {
  if (!integrity || integrity.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Hash chains</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No ledger integrity data available.</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base flex items-center gap-2">
          <Link className="h-4 w-4" />
          Hash chains
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {integrity.map((item) => (
          <div
            key={item.run_dir}
            className={`rounded-md border p-3 ${
              item.valid ? "border-emerald-500/20" : "border-rose-500/20"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="mono text-xs">{item.run_dir}</span>
              <span
                className={`rounded px-2 py-0.5 text-xs ${
                  item.valid
                    ? "bg-emerald-500/10 text-emerald-500"
                    : "bg-rose-500/10 text-rose-500"
                }`}
              >
                {item.valid ? "verified" : "broken"}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground mono truncate">
              {item.ledger_path}
            </p>
            <p className="text-xs text-muted-foreground">{item.entries} entries</p>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
