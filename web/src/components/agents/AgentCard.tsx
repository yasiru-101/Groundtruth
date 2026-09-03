import { Bot, GitPullRequest, Scale, ShieldAlert } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import type { AgentActivity } from "@/types"

const actorIcon: Record<string, React.ReactNode> = {
  auditor: <Scale className="h-4 w-4" />,
  steward: <ShieldAlert className="h-4 w-4" />,
  delivery: <GitPullRequest className="h-4 w-4" />,
  reporting: <Bot className="h-4 w-4" />,
}

interface AgentCardProps {
  activity: AgentActivity
}

export function AgentCard({ activity }: AgentCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="flex items-center gap-2 text-base capitalize">
          {actorIcon[activity.actor] ?? <Bot className="h-4 w-4" />}
          {activity.actor}
        </CardTitle>
        <span className="text-2xl font-bold">{activity.action_count}</span>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          Last: {activity.last_action ?? "—"}
        </p>
        {activity.last_subject && (
          <p className="mt-1 truncate text-xs text-muted-foreground">
            {activity.last_subject}
          </p>
        )}
      </CardContent>
    </Card>
  )
}
