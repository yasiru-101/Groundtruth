import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect } from "react"

import { api } from "@/lib/api"
import { useJobContext } from "@/components/jobs/JobProvider"
import { useToast } from "@/components/ui/toast"

export function useJobs() {
  const queryClient = useQueryClient()
  const { jobId, setJobId } = useJobContext()
  const { toast } = useToast()

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

  const refreshAll = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["score"] })
    queryClient.invalidateQueries({ queryKey: ["discrepancies"] })
    queryClient.invalidateQueries({ queryKey: ["runs"] })
    queryClient.invalidateQueries({ queryKey: ["agents"] })
    queryClient.invalidateQueries({ queryKey: ["report"] })
    queryClient.invalidateQueries({ queryKey: ["plan"] })
    queryClient.invalidateQueries({ queryKey: ["ledger"] })
  }, [queryClient])

  useEffect(() => {
    if (!status.data) return
    if (status.data.status === "completed") {
      toast({ variant: "success", description: `${status.data.command} completed.` })
      refreshAll()
    } else if (status.data.status === "failed") {
      toast({
        variant: "error",
        description: status.data.error || `${status.data.command} failed.`,
      })
      setJobId(null)
    }
  }, [status.data, setJobId, toast, refreshAll])

  return { submit, status, refreshAll }
}
