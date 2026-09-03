import { Outlet } from "react-router-dom"

import { Topbar } from "./Topbar"
import { Sidebar } from "./Sidebar"

interface AppShellProps {
  demoMode: boolean
  projectKey?: string
}

export function AppShell({ demoMode, projectKey }: AppShellProps) {
  return (
    <div className="flex min-h-svh flex-col">
      <Topbar demoMode={demoMode} projectKey={projectKey} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-auto p-4 md:p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
