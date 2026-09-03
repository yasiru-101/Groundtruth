import { ExternalLink } from "lucide-react"

import type { DiscrepancyEvidence } from "@/types"

interface EvidenceLinkProps {
  evidence: DiscrepancyEvidence
}

export function EvidenceLink({ evidence }: EvidenceLinkProps) {
  return (
    <a
      href={evidence.url}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted"
    >
      <span className="font-medium capitalize">{evidence.kind}</span>
      <span className="text-muted-foreground">{evidence.ref}</span>
      <ExternalLink className="h-3 w-3" />
    </a>
  )
}
