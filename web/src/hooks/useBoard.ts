import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export function usePlan() {
  return useQuery({
    queryKey: ["plan"],
    queryFn: api.plan,
  })
}

export function useDelivery() {
  return useQuery({
    queryKey: ["delivery"],
    queryFn: api.delivery,
  })
}

export function useTrace() {
  return useQuery({
    queryKey: ["trace"],
    queryFn: api.trace,
  })
}
