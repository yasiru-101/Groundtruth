import { Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { useSystemStatus } from "@/hooks/useSystemStatus"
import { Agents } from "@/pages/Agents"
import { Discrepancies } from "@/pages/Discrepancies"
import { Integrity } from "@/pages/Integrity"
import { NotFound } from "@/pages/NotFound"
import { Overview } from "@/pages/Overview"
import { Report } from "@/pages/Report"
import { Runs } from "@/pages/Runs"
import { Settings } from "@/pages/Settings"

export default function App() {
  const { demoMode, projectKey } = useSystemStatus()

  return (
    <Routes>
      <Route
        element={
          <AppShell
            demoMode={demoMode}
            projectKey={projectKey}
          />
        }
      >
        <Route path="/" element={<Overview />} />
        <Route path="/discrepancies" element={<Discrepancies />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/report" element={<Report />} />
        <Route path="/integrity" element={<Integrity />} />
        <Route path="/runs" element={<Runs />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  )
}
