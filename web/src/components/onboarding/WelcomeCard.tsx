import { Link } from "react-router-dom"
import { AlertTriangle, HelpCircle, Settings, ShieldCheck, X } from "lucide-react"

import { Button } from "@/components/ui/button"
import { useLocalStorage } from "@/hooks/useLocalStorage"

export function WelcomeCard() {
  const [dismissed, setDismissed] = useLocalStorage("gt.welcome.dismissed", false)

  if (dismissed) return null

  return (
    <div className="rounded-lg border bg-gradient-to-r from-primary/10 to-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <h2 className="text-lg font-semibold">Welcome to Groundtruth</h2>
          <p className="max-w-2xl text-sm text-muted-foreground">
            Jira records what your team <em>believes</em>. Git records what <em>actually</em>{" "}
            happened. Groundtruth diffs the two, files a discrepancy for every gap, and attaches
            commit SHAs and PR links as evidence. Every agent action is written to a hash-chained
            ledger so you can verify nothing was edited after the fact.
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss welcome"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button variant="secondary" asChild>
          <Link to="/discrepancies">
            <AlertTriangle className="mr-2 h-4 w-4" />
            See discrepancies
          </Link>
        </Button>
        <Button variant="secondary" asChild>
          <Link to="/integrity">
            <ShieldCheck className="mr-2 h-4 w-4" />
            Check integrity
          </Link>
        </Button>
        <Button variant="outline" asChild>
          <Link to="/settings">
            <Settings className="mr-2 h-4 w-4" />
            Connect accounts
          </Link>
        </Button>
      </div>

      <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
        <HelpCircle className="h-3 w-3" />
        Click the help icon in the top bar anytime to reopen this guide.
      </p>
    </div>
  )
}
