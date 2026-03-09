import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { apiFetch } from '@/lib/api'
import { Server, Database, Cloud, CheckCircle, XCircle, Brain, Save, Check, Shield, Copy, ExternalLink, Key, Plus, Trash2, AlertTriangle } from 'lucide-react'

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

interface ApiKeyInfo {
  api_key_id: string
  key_prefix: string
  name: string
  created_at: string
  last_used_at: string
  status: string
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

  // API Keys state
  const [apiKeys, setApiKeys] = useState<ApiKeyInfo[]>([])
  const [showGenerateDialog, setShowGenerateDialog] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [generatedKey, setGeneratedKey] = useState<string | null>(null)
  const [isGenerating, setIsGenerating] = useState(false)
  const [revokeKeyId, setRevokeKeyId] = useState<string | null>(null)

  // Cognito credentials state
  const [showCognitoDialog, setShowCognitoDialog] = useState(false)
  const [cognitoClientName, setCognitoClientName] = useState('')
  const [cognitoCredentials, setCognitoCredentials] = useState<{
    client_id: string
    client_secret: string
    token_endpoint: string
    scopes: string[]
  } | null>(null)
  const [isCreatingClient, setIsCreatingClient] = useState(false)

  const loadApiKeys = () => {
    apiFetch<ApiKeyInfo[]>('/admin/api-keys').then(setApiKeys).catch(() => setApiKeys([]))
  }

  useEffect(() => {
    apiFetch<ServerInfo>('/info').then(setInfo).catch(() => setInfo({ name: 'MCP Skills Server', version: 'unknown', storage_backend: 'unknown' }))
    apiFetch<HealthStatus>('/health').then(setHealth).catch(() => setHealth({ status: 'unknown', skills_loaded: 0 }))
    apiFetch<AuthConfig>('/admin/auth-config').then(setAuthConfig).catch(() => {
      setAuthConfig({
        auth_type: 'cognito',
        cognito_enabled: true,
        mcp_server_url: defaultMcpUrl,
      })
    })
    loadApiKeys()

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

  const handleGenerateKey = async () => {
    setIsGenerating(true)
    try {
      const result = await apiFetch<{ api_key: string }>('/admin/api-keys/generate', {
        method: 'POST',
        body: JSON.stringify({ name: newKeyName || 'default' }),
      })
      setGeneratedKey(result.api_key)
      loadApiKeys()
    } catch (e: any) {
      alert(e.message || 'Failed to generate key')
    } finally {
      setIsGenerating(false)
    }
  }

  const handleRevokeKey = async (keyId: string) => {
    try {
      await apiFetch('/admin/api-keys/revoke', {
        method: 'POST',
        body: JSON.stringify({ api_key_id: keyId }),
      })
      loadApiKeys()
    } catch (e: any) {
      alert(e.message || 'Failed to revoke key')
    } finally {
      setRevokeKeyId(null)
    }
  }

  const handleCreateCognitoClient = async () => {
    setIsCreatingClient(true)
    try {
      const result = await apiFetch<{
        client_id: string
        client_secret: string
        token_endpoint: string
        scopes: string[]
      }>('/admin/cognito/create-client', {
        method: 'POST',
        body: JSON.stringify({ client_name: cognitoClientName || 'mcp-client' }),
      })
      setCognitoCredentials(result)
    } catch (e: any) {
      alert(e.message || 'Failed to create client')
    } finally {
      setIsCreatingClient(false)
    }
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

      {/* API Keys Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Key className="h-5 w-5" /> API Keys
          </CardTitle>
          <CardDescription>Manage persistent API keys for MCP server access</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Button
            onClick={() => {
              setNewKeyName('')
              setGeneratedKey(null)
              setShowGenerateDialog(true)
            }}
            className="w-full"
          >
            <Plus className="h-4 w-4 mr-2" />
            Generate New API Key
          </Button>

          {apiKeys.length > 0 && (
            <div className="space-y-2">
              {apiKeys.map((key) => (
                <div
                  key={key.api_key_id}
                  className="flex items-center justify-between p-3 rounded-lg border"
                >
                  <div className="space-y-1 min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-sm">{key.name}</span>
                      <Badge variant={key.status === 'active' ? 'default' : 'secondary'} className="text-xs">
                        {key.status}
                      </Badge>
                    </div>
                    <div className="text-xs text-muted-foreground font-mono">{key.key_prefix}</div>
                    <div className="text-xs text-muted-foreground">
                      Created: {new Date(key.created_at).toLocaleDateString()}
                      {key.last_used_at && key.last_used_at !== 'never' && (
                        <> &middot; Last used: {new Date(key.last_used_at).toLocaleDateString()}</>
                      )}
                    </div>
                  </div>
                  {key.status === 'active' && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive"
                      onClick={() => setRevokeKeyId(key.api_key_id)}
                      title="Revoke key"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}

          {apiKeys.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No API keys configured. Generate one to enable API key authentication.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Generate Key Dialog */}
      <Dialog open={showGenerateDialog} onOpenChange={setShowGenerateDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{generatedKey ? 'API Key Generated' : 'Generate New API Key'}</DialogTitle>
            <DialogDescription>
              {generatedKey
                ? 'Copy your API key now. It will not be shown again.'
                : 'Give your API key a name to help identify it later.'}
            </DialogDescription>
          </DialogHeader>

          {!generatedKey ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="key-name">Key Name</Label>
                <Input
                  id="key-name"
                  placeholder="e.g., production-gateway"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                />
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowGenerateDialog(false)}>
                  Cancel
                </Button>
                <Button onClick={handleGenerateKey} disabled={isGenerating}>
                  {isGenerating ? 'Generating...' : 'Generate'}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <div className="space-y-3">
                <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-amber-800 dark:text-amber-200">
                    This key will only be shown once. Store it in a secure location.
                  </p>
                </div>
                <div className="flex gap-2">
                  <Input
                    value={generatedKey}
                    readOnly
                    className="font-mono text-xs bg-muted"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => handleCopy(generatedKey, 'generatedKey')}
                  >
                    {copiedField === 'generatedKey' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                  </Button>
                </div>
              </div>
              <DialogFooter>
                <Button onClick={() => setShowGenerateDialog(false)}>Done</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Revoke Key Confirmation Dialog */}
      <Dialog open={!!revokeKeyId} onOpenChange={() => setRevokeKeyId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revoke API Key</DialogTitle>
            <DialogDescription>
              Are you sure you want to revoke this API key? Any clients using it will lose access immediately.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevokeKeyId(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => revokeKeyId && handleRevokeKey(revokeKeyId)}
            >
              Revoke
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cognito Credentials Card */}
      {authConfig?.cognito_enabled && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5" /> Cognito Credentials
            </CardTitle>
            <CardDescription>Provision new OAuth 2.0 client credentials for service-to-service access</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              onClick={() => {
                setCognitoClientName('')
                setCognitoCredentials(null)
                setShowCognitoDialog(true)
              }}
              className="w-full"
            >
              <Plus className="h-4 w-4 mr-2" />
              Request Credentials
            </Button>
            <p className="text-xs text-muted-foreground">
              Creates a new Cognito app client with Client Credentials flow. The client secret is shown once and cannot be retrieved later.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Cognito Create Client Dialog */}
      <Dialog open={showCognitoDialog} onOpenChange={setShowCognitoDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{cognitoCredentials ? 'Credentials Created' : 'Create OAuth Client'}</DialogTitle>
            <DialogDescription>
              {cognitoCredentials
                ? 'Copy your credentials now. The client secret will not be shown again.'
                : 'Name your OAuth client to identify it in the Cognito console.'}
            </DialogDescription>
          </DialogHeader>

          {!cognitoCredentials ? (
            <>
              <div className="space-y-2">
                <Label htmlFor="client-name">Client Name</Label>
                <Input
                  id="client-name"
                  placeholder="e.g., my-agent-gateway"
                  value={cognitoClientName}
                  onChange={(e) => setCognitoClientName(e.target.value)}
                />
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setShowCognitoDialog(false)}>
                  Cancel
                </Button>
                <Button onClick={handleCreateCognitoClient} disabled={isCreatingClient}>
                  {isCreatingClient ? 'Creating...' : 'Create Client'}
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <div className="space-y-3">
                <div className="bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex items-start gap-2">
                  <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-amber-800 dark:text-amber-200">
                    The client secret is shown once. Store it securely.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">Client ID</Label>
                  <div className="flex gap-2">
                    <Input value={cognitoCredentials.client_id} readOnly className="font-mono text-xs bg-muted" />
                    <Button variant="outline" size="icon" onClick={() => handleCopy(cognitoCredentials.client_id, 'cognitoClientId')}>
                      {copiedField === 'cognitoClientId' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">Client Secret</Label>
                  <div className="flex gap-2">
                    <Input value={cognitoCredentials.client_secret} readOnly className="font-mono text-xs bg-muted" />
                    <Button variant="outline" size="icon" onClick={() => handleCopy(cognitoCredentials.client_secret, 'cognitoClientSecret')}>
                      {copiedField === 'cognitoClientSecret' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">Token Endpoint</Label>
                  <div className="flex gap-2">
                    <Input value={cognitoCredentials.token_endpoint} readOnly className="font-mono text-xs bg-muted" />
                    <Button variant="outline" size="icon" onClick={() => handleCopy(cognitoCredentials.token_endpoint, 'cognitoTokenEndpoint')}>
                      {copiedField === 'cognitoTokenEndpoint' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">Scopes</Label>
                  <div className="flex gap-2">
                    <Input value={cognitoCredentials.scopes.join(' ')} readOnly className="font-mono text-xs bg-muted" />
                    <Button variant="outline" size="icon" onClick={() => handleCopy(cognitoCredentials.scopes.join(' '), 'cognitoScopes')}>
                      {copiedField === 'cognitoScopes' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label className="text-xs text-muted-foreground">MCP Server URL</Label>
                  <div className="flex gap-2">
                    <Input value={mcpServerUrl} readOnly className="font-mono text-xs bg-muted" />
                    <Button variant="outline" size="icon" onClick={() => handleCopy(mcpServerUrl, 'cognitoMcpUrl')}>
                      {copiedField === 'cognitoMcpUrl' ? <Check className="h-4 w-4 text-green-500" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>
              </div>
              <DialogFooter>
                <Button onClick={() => setShowCognitoDialog(false)}>Done</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>

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
