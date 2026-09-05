import { BookOpen, HelpCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"

export function HelpDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Help">
          <HelpCircle className="h-5 w-5" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            What is Groundtruth?
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm text-muted-foreground">
          <p>
            Jira records what your team <em>believes</em> is happening. Git records what
            <em>actually</em> happened. Groundtruth diffs the two, files a discrepancy for every
            gap, and attaches commit SHAs and PR links as evidence.
          </p>
          <p>
            Every agent action is written to a hash-chained ledger, so you can verify nothing was
            edited after the fact.
          </p>

          <div className="space-y-2">
            <h4 className="font-medium text-foreground">Common terms</h4>
            <ul className="space-y-1">
              <li>
                <strong>Truthfulness score</strong> — a 0–100 weighted measure of how well the
                board matches reality.
              </li>
              <li>
                <strong>Discrepancy</strong> — a specific mismatch (e.g., a merged PR still marked
                open in Jira).
              </li>
              <li>
                <strong>Ledger integrity</strong> — cryptographic verification that the audit trail
                was not tampered with.
              </li>
              <li>
                <strong>Replay</strong> — re-running analysis on artifact files already on disk,
                without calling live APIs.
              </li>
            </ul>
          </div>

          <p>
            Connect GitHub, Jira, and an LLM in Settings. To collect fresh live data, use the CLI:
            <code className="ml-1 rounded bg-muted px-1 py-0.5 text-xs">
              groundtruth --run-mode live audit
            </code>
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}
