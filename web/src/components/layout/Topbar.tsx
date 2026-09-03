import { ModeBadge } from "./ModeBadge"

interface TopbarProps {
  demoMode: boolean
  projectKey?: string
}

export function Topbar({ demoMode, projectKey }: TopbarProps) {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background/95 px-4 backdrop-blur">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary font-bold text-primary-foreground">
          G
        </div>
        <span className="font-semibold tracking-tight">Groundtruth</span>
      </div>
      <div className="ml-auto flex items-center gap-3">
        {projectKey && (
          <span className="mono text-xs text-muted-foreground">{projectKey}</span>
        )}
        <ModeBadge demo={demoMode} />
      </div>
    </header>
  )
}
