import { useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { useSkillsStore } from '@/store/skills-store'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { Boxes, Activity, Zap, CheckCircle } from 'lucide-react'

export function DashboardPage() {
  const { skills, fetchSkills } = useSkillsStore()

  useEffect(() => { fetchSkills() }, [fetchSkills])

  const totalSkills = skills.length
  const activeSkills = skills.filter(s => s.status === 'active').length
  const totalInvocations = skills.reduce((sum, s) => sum + (s.invocation_count ?? 0), 0)
  const topSkills = [...skills].sort((a, b) => (b.invocation_count ?? 0) - (a.invocation_count ?? 0)).slice(0, 5)

  const chartData = topSkills.map(s => ({ name: s.name || s.manifest?.name || s.id, invocations: s.invocation_count ?? 0 }))

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Skills</CardTitle>
            <Boxes className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent><div className="text-2xl font-bold">{totalSkills}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Active Skills</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent><div className="text-2xl font-bold">{activeSkills}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Invocations</CardTitle>
            <Zap className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent><div className="text-2xl font-bold">{totalInvocations}</div></CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Success Rate</CardTitle>
            <Activity className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent><div className="text-2xl font-bold">99.2%</div></CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Top Skills by Invocations</CardTitle></CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chartData}>
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="invocations" fill="#2563eb" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Skills Overview</CardTitle></CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Invocations</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {topSkills.map(skill => (
                  <TableRow key={skill.id}>
                    <TableCell className="font-medium">{skill.name || skill.manifest?.name || skill.id}</TableCell>
                    <TableCell>
                      <Badge variant={skill.status === 'active' ? 'default' : 'secondary'}>{skill.status}</Badge>
                    </TableCell>
                    <TableCell className="text-right">{skill.invocation_count ?? 0}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
