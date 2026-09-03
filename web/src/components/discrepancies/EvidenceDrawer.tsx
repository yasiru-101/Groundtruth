import { EvidenceLink } from "./EvidenceLink"

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { severityColor } from "@/score-band"
import type { DiscrepancyItem } from "@/types"

interface EvidenceDrawerProps {
  item: DiscrepancyItem | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EvidenceDrawer({ item, open, onOpenChange }: EvidenceDrawerProps) {
  if (!item) return null
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle className="text-base">{item.subject}</SheetTitle>
          <SheetDescription>
            <span className={`inline-flex rounded border px-2 py-0.5 text-xs ${severityColor(item.severity)}`}>
              {item.severity}
            </span>{" "}
            <span className="text-xs text-muted-foreground">{item.type}</span>
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-6">
          <div>
            <h4 className="mb-2 text-sm font-medium">Evidence</h4>
            <div className="flex flex-wrap gap-2">
              {item.evidence.map((e, i) => (
                <EvidenceLink key={i} evidence={e} />
              ))}
            </div>
          </div>
          <div>
            <h4 className="mb-2 text-sm font-medium">Proposed action</h4>
            <div className="rounded-md border bg-card p-3 text-sm">
              <p className="font-medium">
                {item.proposed_action.verb} {item.proposed_action.target}
              </p>
              {Object.keys(item.proposed_action.params).length > 0 && (
                <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted p-2 text-xs">
                  {JSON.stringify(item.proposed_action.params, null, 2)}
                </pre>
              )}
              <div className="mt-2 flex gap-2 text-xs text-muted-foreground">
                <span>{item.proposed_action.reversible ? "Reversible" : "Irreversible"}</span>
                <span>{item.proposed_action.requires_approval ? "Needs approval" : "Auto-allowed"}</span>
              </div>
            </div>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
