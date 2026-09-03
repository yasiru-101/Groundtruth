import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { api } from "@/lib/api"

export function useJobs() {
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<string | null>(null)

  const submit = useMutation({
    mutationFn: api.submitJob,
    onSuccess: (data) => {
      setJobId(data.job_id)
    },
  })

  const status = useQuery({
    queryKey: ["jobs", jobId],
    queryFn: () => (jobId ? api.jobStatus(jobId) : null),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const state = query.state.data
      if (!state || state.status === "pending" || state.status === "running") return 1000
      return false
    },
  })

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ["score"] })
    queryClient.invalidateQueries({ queryKey: ["discrepancies"] })
    queryClient.invalidateQueries({ queryKey: ["runs"] })
    queryClient.invalidateQueries({ queryKey: ["agents"] })
    queryClient.invalidateQueries({ queryKey: ["report"] })
    queryClient.invalidateQueries({ queryKey: ["plan"] })
  }

  return { submit, status, refreshAll }
}
