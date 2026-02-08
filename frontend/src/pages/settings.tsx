import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { apiFetch } from '@/lib/api'
import { Server, Database, Cloud, CheckCircle, XCircle } from 'lucide-react'

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

  useEffect(() => {
    apiFetch<ServerInfo>('/info').then(setInfo).catch(() => setInfo({ name: 'MCP Skills Server', version: 'unknown', storage_backend: 'unknown' }))
    apiFetch<HealthStatus>('/health').then(setHealth).catch(() => setHealth({ status: 'unknown', skills_loaded: 0 }))
  }, [])

  const isHealthy = health?.status === 'healthy'

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

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
