import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { useSkillsStore, Skill } from '@/store/skills-store'
import { RefreshCw, MoreHorizontal, Upload, Search, Trash2, Eye } from 'lucide-react'

export function SkillsPage() {
  const navigate = useNavigate()
  const { skills, fetchSkills, reloadSkill, reloadAll, unloadSkill, loading } = useSkillsStore()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  useEffect(() => { fetchSkills() }, [fetchSkills])

  const filtered = skills.filter(s => {
    const name = s.name || s.manifest?.name || s.id || ''
    const matchSearch = name.toLowerCase().includes(search.toLowerCase())
    const matchStatus = statusFilter === 'all' || s.status === statusFilter
    return matchSearch && matchStatus
  })

  const statusVariant = (status: Skill['status']) => {
    switch (status) {
      case 'active': return 'default'
      case 'error': return 'destructive'
      default: return 'secondary'
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Skills</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => reloadAll()} disabled={loading}>
            <RefreshCw className="mr-2 h-4 w-4" /> Reload All
          </Button>
          <Button onClick={() => navigate('/skills/upload')}>
            <Upload className="mr-2 h-4 w-4" /> Upload
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <div className="flex gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input placeholder="Search skills..." value={search} onChange={e => setSearch(e.target.value)} className="pl-9" />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[150px]"><SelectValue placeholder="Status" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Status</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="inactive">Inactive</SelectItem>
                <SelectItem value="error">Error</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Version</TableHead>
                <TableHead className="text-right">Invocations</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map(skill => (
                <TableRow key={skill.id} className="cursor-pointer" onClick={() => navigate(`/skills/${skill.id}`)}>
                  <TableCell className="font-medium">{skill.name || skill.manifest?.name || skill.id}</TableCell>
                  <TableCell className="text-muted-foreground max-w-[300px] truncate">{skill.description || skill.manifest?.description}</TableCell>
                  <TableCell><Badge variant={statusVariant(skill.status)}>{skill.status}</Badge></TableCell>
                  <TableCell>v{skill.version || '1'}</TableCell>
                  <TableCell className="text-right">{skill.invocation_count ?? 0}</TableCell>
                  <TableCell onClick={e => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon"><MoreHorizontal className="h-4 w-4" /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => navigate(`/skills/${skill.id}`)}>
                          <Eye className="mr-2 h-4 w-4" /> View
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => reloadSkill(skill.id)}>
                          <RefreshCw className="mr-2 h-4 w-4" /> Reload
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => unloadSkill(skill.id)} className="text-destructive">
                          <Trash2 className="mr-2 h-4 w-4" /> Unload
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
