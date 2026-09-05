import { createContext, useCallback, useContext, useMemo, useState } from "react"
import type { ReactNode } from "react"

interface JobContextValue {
  jobId: string | null
  setJobId: (id: string | null) => void
}

const JobContext = createContext<JobContextValue | null>(null)

export function JobProvider({ children }: { children: ReactNode }) {
  const [jobId, setJobIdState] = useState<string | null>(null)

  const setJobId = useCallback((id: string | null) => {
    setJobIdState(id)
  }, [])

  const value = useMemo(() => ({ jobId, setJobId }), [jobId, setJobId])

  return <JobContext.Provider value={value}>{children}</JobContext.Provider>
}

export function useJobContext() {
  const ctx = useContext(JobContext)
  if (!ctx) throw new Error("useJobContext must be used within JobProvider")
  return ctx
}
