import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export function useDiscrepancies(filters?: { severity?: string; type?: string }) {
  return useQuery({
    queryKey: ["discrepancies", filters],
    queryFn: () => api.discrepancies(filters),
  })
}
