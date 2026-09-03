import { Badge } from "@/components/ui/badge"

interface ModeBadgeProps {
  demo: boolean
}

export function ModeBadge({ demo }: ModeBadgeProps) {
  return (
    <Badge variant={demo ? "secondary" : "default"}>
      {demo ? "DEMO" : "LIVE"}
    </Badge>
  )
}
