import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { apiFetch } from '@/lib/api'
import { Server, Database, Cloud, CheckCircle, XCircle, Brain, Save, Check } from 'lucide-react'

interface ServerInfo {
  name: string
  version: string
  storage_backend: string
}

interface HealthStatus {
  status: string
  skills_loaded: number
}

export function SettingsPage() {
  const [info, setInfo] = useState<ServerInfo | null>(null)
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [bedrockApiKey, setBedrockApiKey] = useState('')
  const [bedrockEndpoint, setBedrockEndpoint] = useState('')
  const defaultMcpUrl = import.meta.env.VITE_MCP_SERVER_URL || 'https://mcp.openmcpskills.click/mcp'
  const [mcpServerUrl, setMcpServerUrl] = useState(defaultMcpUrl)
  const [isSaving, setIsSaving] = useState(false)
  const [showSuccess, setShowSuccess] = useState(false)

  useEffect(() => {
    apiFetch<ServerInfo>('/info').then(setInfo).catch(() => setInfo({ name: 'MCP Skills Server', version: 'unknown', storage_backend: 'unknown' }))
    apiFetch<HealthStatus>('/health').then(setHealth).catch(() => setHealth({ status: 'unknown', skills_loaded: 0 }))
    
    // Load saved settings from localStorage
    const savedApiKey = localStorage.getItem('bedrock_api_key') || ''
    const savedEndpoint = localStorage.getItem('bedrock_endpoint') || ''
    const savedMcpUrl = localStorage.getItem('mcp_server_url') || defaultMcpUrl
    
    setBedrockApiKey(savedApiKey)
    setBedrockEndpoint(savedEndpoint)
    setMcpServerUrl(savedMcpUrl)
  }, [])

  const handleSaveSettings = () => {
    setIsSaving(true)
    setShowSuccess(false)
    
    // Save to localStorage
    localStorage.setItem('bedrock_api_key', bedrockApiKey)
    localStorage.setItem('bedrock_endpoint', bedrockEndpoint)
    localStorage.setItem('mcp_server_url', mcpServerUrl)
    
    setTimeout(() => {
      setIsSaving(false)
      setShowSuccess(true)
      setTimeout(() => setShowSuccess(false), 3000)
    }, 500)
  }

  const isHealthy = health?.status === 'healthy'

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Brain className="h-5 w-5" /> Model Configuration
          </CardTitle>
          <CardDescription>Configure AWS Bedrock and MCP Server settings</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="bedrock-api-key">Bedrock API Key</Label>
            <Input
              id="bedrock-api-key"
              type="password"
              placeholder="Enter your Bedrock API key"
              value={bedrockApiKey}
              onChange={(e) => {
                setBedrockApiKey(e.target.value)
                setShowSuccess(false)
              }}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="bedrock-endpoint">Bedrock Endpoint</Label>
            <Input
              id="bedrock-endpoint"
              type="text"
              placeholder="e.g., https://bedrock-runtime.us-east-1.amazonaws.com"
              value={bedrockEndpoint}
              onChange={(e) => {
                setBedrockEndpoint(e.target.value)
                setShowSuccess(false)
              }}
            />
            <p className="text-xs text-muted-foreground">Default: Same as deployment region</p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="mcp-server-url">MCP Server URL</Label>
            <Input
              id="mcp-server-url"
              type="text"
              placeholder="https://mcp.openmcpskills.click/mcp"
              value={mcpServerUrl}
              onChange={(e) => {
                setMcpServerUrl(e.target.value)
                setShowSuccess(false)
              }}
            />
          </div>
          <Button onClick={handleSaveSettings} disabled={isSaving} className="w-full">
            {showSuccess ? (
              <>
                <Check className="h-4 w-4 mr-2" />
                Saved Successfully
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                {isSaving ? 'Saving...' : 'Save Settings'}
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" /> Server Information
          </CardTitle>
          <CardDescription>MCP Skills Server configuration</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-between">
            <span className="text-muted-foreground">Server Name</span>
            <span className="font-medium">{info?.name || 'Loading...'}</span>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Version</span>
            <span className="font-medium">{info?.version || 'Loading...'}</span>
          </div>
          <Separator />
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">Health Status</span>
            <Badge variant={isHealthy ? 'default' : 'destructive'} className="flex items-center gap-1">
              {isHealthy ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
              {health?.status || 'Unknown'}
            </Badge>
          </div>
          <Separator />
          <div className="flex justify-between">
            <span className="text-muted-foreground">Skills Loaded</span>
            <span className="font-medium">{health?.skills_loaded ?? 'Loading...'}</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-5 w-5" /> Storage Backend
          </CardTitle>
          <CardDescription>Current storage configuration</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">Backend Type</span>
            <Badge variant="outline" className="flex items-center gap-1">
              <Cloud className="h-3 w-3" />
              {info?.storage_backend || 'Loading...'}
            </Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
