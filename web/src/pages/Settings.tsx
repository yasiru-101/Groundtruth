import { useEffect, useState } from "react"
import { AlertCircle, Brain, CheckCircle2, Cloud, GitBranch, Loader2 } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  useConnections,
  useDisconnect,
  useOAuthConnect,
  useParseUrl,
  useSetGitHubPat,
  useSetGitHubRepo,
  useSetJiraBasic,
  useSetJiraProject,
  useSetLlm,
  useTestConnection,
} from "@/hooks/useConnections"

export function Settings() {
  const { data: connections, isLoading } = useConnections()

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Connect GitHub, Jira, and your LLM provider so Groundtruth can read and write on your behalf.
        </p>
      </div>

      {isLoading || !connections ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading connections...
        </div>
      ) : (
        <Tabs defaultValue="github">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="github" className="gap-2">
              <GitBranch className="h-4 w-4" />
              GitHub
            </TabsTrigger>
            <TabsTrigger value="jira" className="gap-2">
              <Cloud className="h-4 w-4" />
              Jira
            </TabsTrigger>
            <TabsTrigger value="llm" className="gap-2">
              <Brain className="h-4 w-4" />
              LLM
            </TabsTrigger>
          </TabsList>
          <TabsContent value="github">
            <GitHubCard status={connections.github} />
          </TabsContent>
          <TabsContent value="jira">
            <JiraCard status={connections.jira} />
          </TabsContent>
          <TabsContent value="llm">
            <LlmCard status={connections.llm} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}

function GitHubCard({ status }: { status: { connected: boolean; repo_slug: string; login: string; auth_kind: string; oauth_available: boolean } }) {
  const [repoUrl, setRepoUrl] = useState("")
  const [owner, setOwner] = useState("")
  const [name, setName] = useState("")
  const [pat, setPat] = useState("")
  const [message, setMessage] = useState<string | null>(null)

  const parse = useParseUrl()
  const saveRepo = useSetGitHubRepo()
  const save = useSetGitHubPat()
  const test = useTestConnection()
  const disconnect = useDisconnect()
  const oauth = useOAuthConnect("github")

  useEffect(() => {
    if (oauth.result) {
      setMessage(`${oauth.result.status === "success" ? "Connected" : "OAuth failed"}: ${oauth.result.detail}`)
      oauth.clearResult()
    }
  }, [oauth])

  const handleParse = async () => {
    setMessage(null)
    try {
      const result = await parse.mutateAsync(repoUrl)
      if (result.provider === "github" && result.valid) {
        setOwner(result.owner)
        setName(result.name)
        await saveRepo.mutateAsync({ owner: result.owner, name: result.name })
        setMessage(`Parsed and saved as ${result.owner}/${result.name}`)
      } else {
        setMessage("Could not parse GitHub repo URL.")
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Parse failed")
    }
  }

  const handleSave = async () => {
    setMessage(null)
    if (!owner || !name || !pat) {
      setMessage("Owner, repo name, and PAT are required.")
      return
    }
    try {
      await save.mutateAsync({ owner, name, pat })
      setPat("")
      setMessage("GitHub connection saved.")
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed")
    }
  }

  const handleTest = async () => {
    setMessage(null)
    const result = await test.mutateAsync("github")
    setMessage(result.ok ? `Test passed: ${result.message}` : `Test failed: ${result.message}`)
  }

  const canConnectOAuth = status.oauth_available && status.repo_slug && !status.connected

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GitBranch className="h-5 w-5" />
          GitHub
          {status.connected && <BadgeOk />}
        </CardTitle>
        <CardDescription>
          Paste your repo URL and a personal access token with <code>repo</code> scope, or connect via OAuth.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <StatusRow label="Repo" value={status.repo_slug || "Not set"} />
        {status.login && <StatusRow label="User" value={status.login} />}

        {status.oauth_available && (
          <div className="rounded-md border border-accent/50 bg-accent/10 p-3">
            <p className="text-sm font-medium text-accent-foreground">OAuth connected app configured</p>
            <p className="text-xs text-muted-foreground">
              You can connect with one click after setting the repo below.
            </p>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="gh-url">Repository URL</Label>
          <div className="flex gap-2">
            <Input
              id="gh-url"
              placeholder="https://github.com/owner/repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
            />
            <Button variant="secondary" onClick={handleParse} disabled={parse.isPending || !repoUrl}>
              {parse.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Parse"}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="gh-owner">Owner</Label>
            <Input id="gh-owner" value={owner} onChange={(e) => setOwner(e.target.value)} placeholder="owner" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="gh-name">Repo</Label>
            <Input id="gh-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="repo" />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="gh-pat">Personal Access Token</Label>
          <Input
            id="gh-pat"
            type="password"
            value={pat}
            onChange={(e) => setPat(e.target.value)}
            placeholder="ghp_..."
          />
        </div>

        {message && <Alert text={message} />}

        <div className="flex flex-wrap gap-2 pt-2">
          <Button onClick={handleSave} disabled={save.isPending}>
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save GitHub"}
          </Button>
          {canConnectOAuth && (
            <Button variant="default" onClick={() => oauth.start()} disabled={oauth.isPending}>
              {oauth.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Connect with GitHub"}
            </Button>
          )}
          <Button variant="outline" onClick={handleTest} disabled={test.isPending}>
            {test.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test"}
          </Button>
          {status.connected && (
            <Button variant="ghost" className="text-destructive" onClick={() => disconnect.mutate("github")}>
              Disconnect
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function JiraCard({ status }: { status: { connected: boolean; site_url: string; project_key: string; email: string; auth_kind: string; oauth_available: boolean } }) {
  const [url, setUrl] = useState("")
  const [baseUrl, setBaseUrl] = useState("")
  const [projectKey, setProjectKey] = useState("")
  const [email, setEmail] = useState("")
  const [token, setToken] = useState("")
  const [message, setMessage] = useState<string | null>(null)

  const parse = useParseUrl()
  const saveProject = useSetJiraProject()
  const save = useSetJiraBasic()
  const test = useTestConnection()
  const disconnect = useDisconnect()
  const oauth = useOAuthConnect("jira")

  useEffect(() => {
    if (oauth.result) {
      setMessage(`${oauth.result.status === "success" ? "Connected" : "OAuth failed"}: ${oauth.result.detail}`)
      oauth.clearResult()
    }
  }, [oauth])

  const handleParse = async () => {
    setMessage(null)
    try {
      const result = await parse.mutateAsync(url)
      if (result.provider === "jira" && result.valid) {
        setBaseUrl(result.base_url)
        setProjectKey(result.project_key)
        await saveProject.mutateAsync({ base_url: result.base_url, project_key: result.project_key })
        setMessage(`Parsed and saved site ${result.base_url}${result.project_key ? `, project ${result.project_key}` : ""}`)
      } else {
        setMessage("Could not parse Jira URL.")
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Parse failed")
    }
  }

  const handleSave = async () => {
    setMessage(null)
    if (!baseUrl || !projectKey || !email || !token) {
      setMessage("Site URL, project key, email, and API token are required.")
      return
    }
    try {
      await save.mutateAsync({ base_url: baseUrl, project_key: projectKey, email, api_token: token })
      setToken("")
      setMessage("Jira connection saved.")
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed")
    }
  }

  const handleTest = async () => {
    setMessage(null)
    const result = await test.mutateAsync("jira")
    setMessage(result.ok ? `Test passed: ${result.message}` : `Test failed: ${result.message}`)
  }

  const canConnectOAuth = status.oauth_available && status.site_url && status.project_key && !status.connected

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Cloud className="h-5 w-5" />
          Jira
          {status.connected && <BadgeOk />}
        </CardTitle>
        <CardDescription>
          Paste a Jira project URL and your email + API token, or connect via OAuth.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <StatusRow label="Site" value={status.site_url || "Not set"} />
        <StatusRow label="Project" value={status.project_key || "Not set"} />
        {status.email && <StatusRow label="Email" value={status.email} />}

        {status.oauth_available && (
          <div className="rounded-md border border-accent/50 bg-accent/10 p-3">
            <p className="text-sm font-medium text-accent-foreground">OAuth connected app configured</p>
            <p className="text-xs text-muted-foreground">
              Paste your project URL below, then connect with one click.
            </p>
          </div>
        )}

        <div className="space-y-2">
          <Label htmlFor="jira-url">Project URL</Label>
          <div className="flex gap-2">
            <Input
              id="jira-url"
              placeholder="https://x.atlassian.net/jira/software/projects/GT/boards/1"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
            <Button variant="secondary" onClick={handleParse} disabled={parse.isPending || !url}>
              {parse.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Parse"}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="jira-site">Site URL</Label>
            <Input id="jira-site" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://x.atlassian.net" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="jira-key">Project Key</Label>
            <Input id="jira-key" value={projectKey} onChange={(e) => setProjectKey(e.target.value)} placeholder="GT" />
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="jira-email">Email</Label>
          <Input id="jira-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
        </div>

        <div className="space-y-2">
          <Label htmlFor="jira-token">API Token</Label>
          <Input id="jira-token" type="password" value={token} onChange={(e) => setToken(e.target.value)} placeholder="ATATT..." />
        </div>

        {message && <Alert text={message} />}

        <div className="flex flex-wrap gap-2 pt-2">
          <Button onClick={handleSave} disabled={save.isPending}>
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save Jira"}
          </Button>
          {canConnectOAuth && (
            <Button variant="default" onClick={() => oauth.start()} disabled={oauth.isPending}>
              {oauth.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Connect with Jira"}
            </Button>
          )}
          <Button variant="outline" onClick={handleTest} disabled={test.isPending}>
            {test.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test"}
          </Button>
          {status.connected && (
            <Button variant="ghost" className="text-destructive" onClick={() => disconnect.mutate("jira")}>
              Disconnect
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

const LLM_PRESETS: Record<string, { base_url: string; model: string }> = {
  "OpenAI": { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  "Groq": { base_url: "https://api.groq.com/openai/v1", model: "llama-3.1-8b-instant" },
  "Gemini": { base_url: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-1.5-flash" },
  "OpenRouter": { base_url: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini" },
  "Custom": { base_url: "", model: "" },
}

function LlmCard({ status }: { status: { connected: boolean; provider: string; base_url: string; model: string; key_last4: string } }) {
  const [provider, setProvider] = useState(status.provider || "OpenAI")
  const [baseUrl, setBaseUrl] = useState(status.base_url || "")
  const [model, setModel] = useState(status.model || "")
  const [apiKey, setApiKey] = useState("")
  const [message, setMessage] = useState<string | null>(null)

  const save = useSetLlm()
  const test = useTestConnection()
  const disconnect = useDisconnect()

  const applyPreset = (name: string) => {
    setProvider(name)
    const preset = LLM_PRESETS[name]
    if (preset) {
      setBaseUrl(preset.base_url)
      setModel(preset.model)
    }
  }

  const handleSave = async () => {
    setMessage(null)
    if (!baseUrl || !model || !apiKey) {
      setMessage("Provider, base URL, model, and API key are required.")
      return
    }
    try {
      await save.mutateAsync({ provider, base_url: baseUrl, model, api_key: apiKey })
      setApiKey("")
      setMessage("LLM connection saved.")
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Save failed")
    }
  }

  const handleTest = async () => {
    setMessage(null)
    const result = await test.mutateAsync("llm")
    setMessage(result.ok ? `Test passed: ${result.message}` : `Test failed: ${result.message}`)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5" />
          LLM Provider
          {status.connected && <BadgeOk />}
        </CardTitle>
        <CardDescription>
          Choose a preset or enter a custom OpenAI-compatible endpoint.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <StatusRow label="Provider" value={status.provider || "Not set"} />
        <StatusRow label="Model" value={status.model || "Not set"} />
        {status.key_last4 && <StatusRow label="Key" value={`••••${status.key_last4}`} />}

        <div className="space-y-2">
          <Label htmlFor="llm-provider">Provider preset</Label>
          <select
            id="llm-provider"
            value={provider}
            onChange={(e) => applyPreset(e.target.value)}
            className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          >
            {Object.keys(LLM_PRESETS).map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="llm-base">Base URL</Label>
          <Input id="llm-base" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" />
        </div>

        <div className="space-y-2">
          <Label htmlFor="llm-model">Model</Label>
          <Input id="llm-model" value={model} onChange={(e) => setModel(e.target.value)} placeholder="gpt-4o-mini" />
        </div>

        <div className="space-y-2">
          <Label htmlFor="llm-key">API Key</Label>
          <Input id="llm-key" type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="sk-..." />
        </div>

        {message && <Alert text={message} />}

        <div className="flex gap-2 pt-2">
          <Button onClick={handleSave} disabled={save.isPending}>
            {save.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Save LLM"}
          </Button>
          <Button variant="outline" onClick={handleTest} disabled={test.isPending}>
            {test.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : "Test"}
          </Button>
          {status.connected && (
            <Button variant="ghost" className="text-destructive" onClick={() => disconnect.mutate("llm")}>
              Disconnect
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  )
}

function BadgeOk() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-accent/20 px-2 py-0.5 text-xs font-medium text-accent-foreground">
      <CheckCircle2 className="h-3 w-3" />
      Connected
    </span>
  )
}

function Alert({ text }: { text: string }) {
  const isError = text.toLowerCase().includes("fail") || text.toLowerCase().includes("could not") || text.toLowerCase().includes("required")
  return (
    <div className={`flex items-start gap-2 rounded-md border px-3 py-2 text-sm ${isError ? "border-destructive/50 text-destructive" : "border-accent/50 text-accent-foreground"}`}>
      {isError ? <AlertCircle className="h-4 w-4 shrink-0" /> : <CheckCircle2 className="h-4 w-4 shrink-0" />}
      <span>{text}</span>
    </div>
  )
}
