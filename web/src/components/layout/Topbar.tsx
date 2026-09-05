import { Link } from "react-router-dom"
import { Brain, Cloud, GitBranch } from "lucide-react"

import { HelpDialog } from "@/components/onboarding/HelpDialog"
import { ModeBadge } from "./ModeBadge"
import { MobileNav } from "./MobileNav"
import { useSystemStatus } from "@/hooks/useSystemStatus"

interface TopbarProps {
  demoMode: boolean
  projectKey?: string
}

export function Topbar({ demoMode, projectKey }: TopbarProps) {
  const { connections } = useSystemStatus()

  const github = connections.data?.github
  const jira = connections.data?.jira
  const llm = connections.data?.llm

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background/95 px-4 backdrop-blur">
      <MobileNav />
      <Link to="/" className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary font-bold text-primary-foreground">
          G
        </div>
        <div className="flex flex-col">
          <span className="font-semibold leading-none tracking-tight">Groundtruth</span>
          <span className="hidden text-[10px] text-muted-foreground sm:inline">
            Keeps your Jira board honest
          </span>
        </div>
      </Link>

      <div className="ml-auto flex items-center gap-3">
        {projectKey && (
          <span className="mono hidden text-xs text-muted-foreground sm:inline">{projectKey}</span>
        )}

        <div className="hidden items-center gap-1.5 rounded-md border px-2 py-1 sm:flex">
          <ConnectionDot connected={github?.connected} icon={GitBranch} label="GitHub" />
          <ConnectionDot connected={jira?.connected} icon={Cloud} label="Jira" />
          <ConnectionDot connected={llm?.connected} icon={Brain} label="LLM" />
        </div>

        <HelpDialog />
        <ModeBadge demo={demoMode} />
      </div>
    </header>
  )
}

function ConnectionDot({
  connected,
  icon: Icon,
  label,
}: {
  connected?: boolean
  icon: typeof GitBranch
  label: string
}) {
  return (
    <Link
      to="/settings"
      className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      title={`${label}: ${connected ? "connected" : "not connected"}`}
    >
      <Icon className={`h-3.5 w-3.5 ${connected ? "text-emerald-500" : "text-muted-foreground"}`} />
      <span className="sr-only">{label}</span>
    </Link>
  )
}
