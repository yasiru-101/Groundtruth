export function scoreBand(value: number): "high" | "mid" | "low" {
  if (value >= 0.85) return "high"
  if (value >= 0.6) return "mid"
  return "low"
}

export function scoreColorClass(value: number): string {
  const band = scoreBand(value)
  if (band === "high") return "text-emerald-500"
  if (band === "mid") return "text-amber-500"
  return "text-rose-500"
}

export function scoreBgClass(value: number): string {
  if (value >= 0.85) return "bg-emerald-500"
  if (value >= 0.6) return "bg-amber-500"
  return "bg-rose-500"
}

export function severityColor(severity: string): string {
  switch (severity.toLowerCase()) {
    case "high":
    case "critical":
      return "bg-rose-500/10 text-rose-500 border-rose-500/20"
    case "medium":
      return "bg-amber-500/10 text-amber-500 border-amber-500/20"
    case "low":
      return "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
    default:
      return "bg-secondary text-secondary-foreground"
  }
}
