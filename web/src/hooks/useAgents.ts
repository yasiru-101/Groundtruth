import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export function useAgentsSummary() {
  return useQuery({
    queryKey: ["agents", "summary"],
    queryFn: api.agents,
  })
}
