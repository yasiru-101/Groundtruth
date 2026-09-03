import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export function useLedger() {
  return useQuery({
    queryKey: ["ledger"],
    queryFn: api.ledger,
  })
}
