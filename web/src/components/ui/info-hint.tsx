import { HelpCircle } from "lucide-react"

interface InfoHintProps {
  text: string
}

export function InfoHint({ text }: InfoHintProps) {
  return (
    <span
      className="inline-flex cursor-help align-text-bottom text-muted-foreground hover:text-foreground"
      title={text}
      aria-label={text}
    >
      <HelpCircle className="h-3.5 w-3.5" />
    </span>
  )
}
