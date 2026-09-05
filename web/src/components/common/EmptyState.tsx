import { Link } from "react-router-dom"
import type { LucideIcon } from "lucide-react"

import { Button } from "@/components/ui/button"

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  action?: {
    to: string
    label: string
  }
  onAction?: () => void
  actionLabel?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  onAction,
  actionLabel,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed p-8 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
        <Icon className="h-6 w-6 text-muted-foreground" />
      </div>
      <h3 className="mt-4 text-sm font-medium">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>
      {action && (
        <Button className="mt-4" asChild>
          <Link to={action.to}>{action.label}</Link>
        </Button>
      )}
      {onAction && actionLabel && (
        <Button className="mt-4" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  )
}
