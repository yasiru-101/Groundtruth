import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export function useRuns() {
  return useQuery({
    queryKey: ["runs"],
    queryFn: api.runs,
  })
}
