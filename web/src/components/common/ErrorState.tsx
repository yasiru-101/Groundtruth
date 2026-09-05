import { AlertCircle } from "lucide-react"

import { Button } from "@/components/ui/button"
import { isApiError } from "@/lib/query"

interface ErrorStateProps {
  title?: string
  error: unknown
  retry?: () => void
}

export function ErrorState({ title = "Something went wrong", error, retry }: ErrorStateProps) {
  let message = isApiError(error) ? error.message : error instanceof Error ? error.message : "Unknown error"

  const isGatewayError =
    (isApiError(error) && (error.status === 502 || error.status === 503 || error.status === 504)) ||
    message.includes("502") ||
    message.includes("Failed to fetch")

  if (isGatewayError) {
    message = "Cannot connect to the backend server (502 Bad Gateway). Please ensure 'python -m groundtruth.api' is running in your terminal."
  }

  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-destructive/30 bg-destructive/5 p-8 text-center">
      <AlertCircle className="h-8 w-8 text-destructive" />
      <h3 className="mt-4 text-sm font-medium">{title}</h3>
      <p className="mt-1 max-w-sm text-sm text-destructive">{message}</p>
      {retry && (
        <Button className="mt-4" variant="outline" onClick={retry}>
          Retry
        </Button>
      )}
    </div>
  )
}
