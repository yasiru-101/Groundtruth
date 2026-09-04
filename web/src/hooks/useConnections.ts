import { useEffect, useRef, useState } from "react"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { api } from "@/lib/api"

const KEY = ["connections"]

export function useConnections() {
  return useQuery({
    queryKey: KEY,
    queryFn: api.connections,
  })
}

export function useParseUrl() {
  return useMutation({
    mutationFn: api.parseUrl,
  })
}

export function useSetGitHubRepo() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ owner, name }: { owner: string; name: string }) =>
      api.setGitHubRepo(owner, name),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useSetGitHubPat() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ owner, name, pat }: { owner: string; name: string; pat: string }) =>
      api.setGitHubPat(owner, name, pat),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useSetJiraProject() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ base_url, project_key }: { base_url: string; project_key: string }) =>
      api.setJiraProject(base_url, project_key),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useSetJiraBasic() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      base_url,
      project_key,
      email,
      api_token,
    }: {
      base_url: string
      project_key: string
      email: string
      api_token: string
    }) => api.setJiraBasic(base_url, project_key, email, api_token),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useSetLlm() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      provider,
      base_url,
      model,
      api_key,
    }: {
      provider: string
      base_url: string
      model: string
      api_key: string
    }) => api.setLlm(provider, base_url, model, api_key),
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export function useTestConnection() {
  return useMutation({
    mutationFn: api.testConnection,
  })
}

export function useDisconnect() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.disconnect,
    onSuccess: () => client.invalidateQueries({ queryKey: KEY }),
  })
}

export interface OAuthResult {
  status: "success" | "error"
  detail: string
  provider: string
}

export function useOAuthConnect(provider: "github" | "jira") {
  const client = useQueryClient()
  const [result, setResult] = useState<OAuthResult | null>(null)
  const popupRef = useRef<Window | null>(null)
  const pollRef = useRef<number | null>(null)

  const start = useMutation({
    mutationFn: api.oauthStart,
    onSuccess: ({ authorize_url }) => {
      const width = 500
      const height = 700
      const left = window.screenX + (window.outerWidth - width) / 2
      const top = window.screenY + (window.outerHeight - height) / 2
      const features = `width=${width},height=${height},left=${left},top=${top},popup=1`
      const popup = window.open(authorize_url, `groundtruth-oauth-${provider}`, features)
      popupRef.current = popup

      if (popup) {
        pollRef.current = window.setInterval(() => {
          if (popup.closed) {
            if (pollRef.current) window.clearInterval(pollRef.current)
            client.invalidateQueries({ queryKey: KEY })
          }
        }, 500)
      } else {
        // Popup blocked — fall back to full redirect.
        window.location.href = authorize_url
      }
    },
  })

  useEffect(() => {
    function onMessage(event: MessageEvent) {
      if (event.source !== popupRef.current) return
      if (event.origin && event.origin !== window.location.origin) return
      const data = event.data
      if (!data || data.source !== "groundtruth-oauth") return
      setResult({
        status: data.status,
        detail: data.detail || "",
        provider: data.provider || provider,
      })
      client.invalidateQueries({ queryKey: KEY })
      if (popupRef.current && !popupRef.current.closed) {
        popupRef.current.close()
      }
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
    window.addEventListener("message", onMessage)
    return () => window.removeEventListener("message", onMessage)
  }, [client, provider])

  useEffect(() => {
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [])

  return {
    start: () => start.mutate(provider),
    isPending: start.isPending,
    result,
    clearResult: () => setResult(null),
  }
}
