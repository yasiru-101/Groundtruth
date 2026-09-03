import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export function useScoreLatest() {
  return useQuery({
    queryKey: ["score", "latest"],
    queryFn: api.scoreLatest,
  })
}

export function useScoreHistory() {
  return useQuery({
    queryKey: ["score", "history"],
    queryFn: api.scoreHistory,
  })
}
