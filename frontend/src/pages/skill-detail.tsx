import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { useSkillsStore, InvocationLog, SkillVersion } from '@/store/skills-store'
import { ArrowLeft, RefreshCw, History, FileText, Activity, BookOpen } from 'lucide-react'
import ReactMarkdown from 'react-markdown'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export function SkillDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { skills, fetchSkills, reloadSkill, getSkillLogs, getSkillVersions, rollbackSkill } = useSkillsStore()
  const [logs, setLogs] = useState<InvocationLog[]>([])
  const [versions, setVersions] = useState<SkillVersion[]>([])
  const [instructions, setInstructions] = useState<string>('')

  const skill = skills.find(s => s.id === id)
  const skillName = skill?.name || skill?.manifest?.name || skill?.id || ''
  const skillDesc = skill?.description || skill?.manifest?.description || ''
  const skillVersion = skill?.version || skill?.manifest?.metadata?.version || '-'
  const skillAuthor = skill?.author || skill?.manifest?.metadata?.author || 'Unknown'
  const skillTags: string[] = skill?.tags || skill?.manifest?.metadata?.tags || []

  useEffect(() => {
    if (!skills.length) fetchSkills()
  }, [skills.length, fetchSkills])

  useEffect(() => {
    if (id) {
      getSkillLogs(id).then(setLogs)
      getSkillVersions(id).then(setVersions)
      fetch(`${API_BASE_URL}/admin/skills/${id}/instructions`)
        .then(r => r.json())
        .then(data => setInstructions(data.instructions || ''))
        .catch(() => setInstructions(''))
    }
  }, [id, getSkillLogs, getSkillVersions])

  if (!skill) return <div className="p-8">Skill not found</div>

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate('/skills')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold">{skillName}</h1>
          <p className="text-muted-foreground">{skillDesc}</p>
        </div>
        <Badge variant={skill.status === 'active' ? 'default' : 'secondary'}>{skill.status}</Badge>
        <Button variant="outline" onClick={() => reloadSkill(skill.id)}>
          <RefreshCw className="mr-2 h-4 w-4" /> Reload
        </Button>
      </div>

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview"><FileText className="mr-2 h-4 w-4" />Overview</TabsTrigger>
          <TabsTrigger value="instructions"><BookOpen className="mr-2 h-4 w-4" />Instructions</TabsTrigger>
          <TabsTrigger value="logs"><Activity className="mr-2 h-4 w-4" />Logs</TabsTrigger>
          <TabsTrigger value="versions"><History className="mr-2 h-4 w-4" />Versions</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Version</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold">{skillVersion}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Invocations</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold">{skill.invocation_count ?? 0}</div></CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm">Author</CardTitle></CardHeader>
              <CardContent><div className="text-2xl font-bold">{skillAuthor}</div></CardContent>
            </Card>
          </div>
          {skillTags.length > 0 && (
            <Card>
              <CardHeader><CardTitle>Tags</CardTitle></CardHeader>
              <CardContent className="flex gap-2">
                {skillTags.map(tag => <Badge key={tag} variant="outline">{tag}</Badge>)}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="instructions">
          <Card>
            <CardHeader>
              <CardTitle>Skill Instructions</CardTitle>
              <CardDescription>The complete SKILL.md content</CardDescription>
            </CardHeader>
            <CardContent className="prose prose-sm dark:prose-invert max-w-none">
              {instructions ? (
                <ReactMarkdown>{instructions}</ReactMarkdown>
              ) : (
                <p className="text-muted-foreground">No instructions available</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="logs">
          <Card>
            <CardHeader>
              <CardTitle>Invocation Logs</CardTitle>
              <CardDescription>Recent invocations for this skill</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Time</TableHead>
                    <TableHead>Method</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {logs.length === 0 ? (
                    <TableRow><TableCell colSpan={4} className="text-center text-muted-foreground">No logs yet</TableCell></TableRow>
                  ) : logs.map((log, i) => (
                    <TableRow key={i}>
                      <TableCell>{new Date(log.invoked_at.split('#')[0]).toLocaleString()}</TableCell>
                      <TableCell>{log.method}</TableCell>
                      <TableCell>{log.duration_ms ? `${log.duration_ms}ms` : '-'}</TableCell>
                      <TableCell>
                        <Badge variant={log.status === 'success' ? 'default' : 'destructive'}>{log.status}</Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="versions">
          <Card>
            <CardHeader>
              <CardTitle>Version History</CardTitle>
              <CardDescription>All versions of this skill</CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Version</TableHead>
                    <TableHead>Published</TableHead>
                    <TableHead className="w-[100px]"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {versions.length === 0 ? (
                    <TableRow><TableCell colSpan={3} className="text-center text-muted-foreground">No versions</TableCell></TableRow>
                  ) : versions.map(v => (
                    <TableRow key={v.version}>
                      <TableCell className="font-medium">v{v.version}</TableCell>
                      <TableCell>{v.published_at ? new Date(v.published_at).toLocaleString() : '-'}</TableCell>
                      <TableCell>
                        {v.version !== skill.version && (
                          <Button variant="outline" size="sm" onClick={() => rollbackSkill(skill.id, v.version)}>
                            Rollback
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
