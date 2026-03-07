import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { apiFetch } from '@/lib/api'
import { Server, Database, Cloud, CheckCircle, XCircle, Brain, Save, Check, Shield, Copy, ExternalLink } from 'lucide-react'

interface ServerInfo {
  name: string
  version: string
  storage_backend: string
}

interface HealthStatus {
  status: string
  skills_loaded: number
}

interface AuthConfig {
  auth_type: 'cognito' | 'api_key' | 'none'
  cognito_enabled: boolean
  cognito_region?: string
  cognito_user_pool_id?: string
  token_endpoint?: string
  client_id?: string
  scopes?: string
  mcp_server_url: string
}

export function SettingsPage() {
  const [info, setInfo] = useState<ServerInfo | null>(null)
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [authConfig, setAuthConfig] = useState<AuthConfig | null>(null)
  const [bedrockApiKey, setBedrockApiKey] = useState('')
  const [bedrockEndpoint, setBedrockEndpoint] = useState('')
  const defaultMcpUrl = import.meta.env.VITE_MCP_SERVER_URL || 'https://mcp.openmcpskills.click/mcp'
  const [mcpServerUrl, setMcpServerUrl] = useState(defaultMcpUrl)
  const [isSaving, setIsSaving] = useState(false)
  const [showSuccess, setShowSuccess] = useState(false)
  
  // Copy state for different fields
  const [copiedField, setCopiedField] = useState<string | null>(null)

  useEffect(() => {
    apiFetch<ServerInfo>('/info').then(setInfo).catch(() => setInfo({ name: 'MCP Skills Server', version: 'unknown', storage_backend: 'unknown' }))
    apiFetch<HealthStatus>('/health').then(setHealth).catch(() => setHealth({ status: 'unknown', skills_loaded: 0 }))
    apiFetch<AuthConfig>('/admin/auth-config').then(setAuthConfig).catch(() => {
      // Fallback to default config if endpoint not available
      setAuthConfig({
        auth_type: 'cognito',
        cognito_enabled: true,
        mcp_server_url: defaultMcpUrl,
      })
    })
    
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

  const handleCopy = async (text: string, field: string) => {
    await navigator.clipboard.writeText(text)
    setCopiedField(field)
    setTimeout(() => setCopiedField(null), 2000)
  }

  const isHealthy = health?.status === 'healthy'

  // OAuth configuration values (from backend or defaults)
  const oauthConfig = {
    tokenEndpoint: authConfig?.token_endpoint || 'https://openmcpskills-1772838404.auth.us-east-1.amazoncognito.com/oauth2/token',
    clientId: authConfig?.client_id || '(Contact administrator)',
    scopes: authConfig?.scopes || 'openmcpskills-api/mcp openmcpskills-api/read',
    mcpServerUrl: mcpServerUrl,
  }

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
            <Shield className="h-5 w-5" /> MCP Authentication
          </CardTitle>
          <CardDescription>OAuth 2.0 credentials for MCP server integration (Quick Suite / AgentCore compatible)</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex justify-between items-center">
            <span className="text-muted-foreground">Authentication Type</span>
            <Badge variant={authConfig?.cognito_enabled ? 'default' : 'secondary'}>
              {authConfig?.cognito_enabled ? 'OAuth 2.0 (Cognito S2S)' : 'Disabled'}
            </Badge>
          </div>
          <Separator />
          
          {authConfig?.cognito_enabled && (
            <div className="space-y-4">
              {/* MCP Server URL */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">MCP Server URL</Label>
                <div className="flex gap-2">
                  <Input
                    value={oauthConfig.mcpServerUrl}
                    readOnly
                    className="font-mono text-xs bg-muted"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleCopy(oauthConfig.mcpServerUrl, 'mcpUrl')}
                    title="Copy MCP Server URL"
                  >
                    {copiedField === 'mcpUrl' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              {/* Token Endpoint */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Token Endpoint</Label>
                <div className="flex gap-2">
                  <Input
                    value={oauthConfig.tokenEndpoint}
                    readOnly
                    className="font-mono text-xs bg-muted"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleCopy(oauthConfig.tokenEndpoint, 'tokenEndpoint')}
                    title="Copy Token Endpoint"
                  >
                    {copiedField === 'tokenEndpoint' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              {/* Client ID */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Client ID</Label>
                <div className="flex gap-2">
                  <Input
                    value={oauthConfig.clientId}
                    readOnly
                    className="font-mono text-xs bg-muted"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleCopy(oauthConfig.clientId, 'clientId')}
                    title="Copy Client ID"
                    disabled={oauthConfig.clientId === '(Contact administrator)'}
                  >
                    {copiedField === 'clientId' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              {/* Scopes */}
              <div className="space-y-2">
                <Label className="text-xs text-muted-foreground">Scopes</Label>
                <div className="flex gap-2">
                  <Input
                    value={oauthConfig.scopes}
                    readOnly
                    className="font-mono text-xs bg-muted"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleCopy(oauthConfig.scopes, 'scopes')}
                    title="Copy Scopes"
                  >
                    {copiedField === 'scopes' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>

              <Separator />

              {/* Quick Suite Integration Guide */}
              <div className="bg-blue-50 dark:bg-blue-950 rounded-lg p-4 space-y-2">
                <h4 className="font-medium text-sm flex items-center gap-2">
                  <ExternalLink className="h-4 w-4" />
                  Quick Suite Integration
                </h4>
                <p className="text-xs text-muted-foreground">
                  In Amazon Quick Suite, add an MCP Integration with these settings:
                </p>
                <ul className="text-xs text-muted-foreground list-disc list-inside space-y-1">
                  <li>Authentication Type: <code className="bg-muted px-1 rounded">OAuth 2.0 / Service Account</code></li>
                  <li>Grant Type: <code className="bg-muted px-1 rounded">Client Credentials</code></li>
                  <li>Client Secret: <code className="bg-muted px-1 rounded">(Obtain from administrator)</code></li>
                </ul>
              </div>

              <p className="text-xs text-muted-foreground">
                Use OAuth 2.0 Client Credentials flow to obtain an access token, then include it as 
                <code className="bg-muted px-1 mx-1 rounded">Authorization: Bearer &lt;token&gt;</code> 
                header in MCP requests.
              </p>
            </div>
          )}

          {!authConfig?.cognito_enabled && (
            <p className="text-sm text-muted-foreground">
              Authentication is currently disabled. Contact your administrator to enable OAuth 2.0 authentication.
            </p>
          )}
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
