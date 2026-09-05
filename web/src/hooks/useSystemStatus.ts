import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export function useSystemStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: api.health,
  })

  const demo = useQuery({
    queryKey: ["demo"],
    queryFn: api.demo,
  })

  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: api.connections,
  })

  const connectedCount =
    (connections.data?.github.connected ? 1 : 0) +
    (connections.data?.jira.connected ? 1 : 0) +
    (connections.data?.llm.connected ? 1 : 0)

  return {
    health,
    demo,
    connections,
    isOffline: Boolean(health.error),
    demoMode: health.data?.demo_mode ?? true,
    artifactsDir: health.data?.artifacts_dir ?? "",
    projectKey: demo.data?.project_key,
    runCount: demo.data?.run_count ?? 0,
    connectedCount,
    isLoading: health.isLoading || demo.isLoading || connections.isLoading,
  }
}
