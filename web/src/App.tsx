import { useQuery } from "@tanstack/react-query"
import { Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { api } from "@/lib/api"
import { Agents } from "@/pages/Agents"
import { Discrepancies } from "@/pages/Discrepancies"
import { Integrity } from "@/pages/Integrity"
import { Overview } from "@/pages/Overview"
import { Report } from "@/pages/Report"
import { Runs } from "@/pages/Runs"

export default function App() {
  const demo = useQuery({
    queryKey: ["demo"],
    queryFn: api.demo,
  })
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
  })

  return (
    <Routes>
      <Route
        element={
          <AppShell
            demoMode={health.data?.demo_mode ?? true}
            projectKey={demo.data?.project_key}
          />
        }
      >
        <Route path="/" element={<Overview />} />
        <Route path="/discrepancies" element={<Discrepancies />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/report" element={<Report />} />
        <Route path="/integrity" element={<Integrity />} />
        <Route path="/runs" element={<Runs />} />
      </Route>
    </Routes>
  )
}
