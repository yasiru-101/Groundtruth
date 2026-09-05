import { ApiError } from "@/lib/api"

export function isNotFound(err: unknown): boolean {
  return err instanceof ApiError && err.status === 404
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError
}

export function apiRetry(failureCount: number, err: unknown): boolean {
  if (isNotFound(err)) return false
  return failureCount < 3
}
