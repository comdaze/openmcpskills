import { useState, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSkillsStore } from '@/store/skills-store'
import { Upload, CheckCircle, XCircle, FileArchive, Github, Loader2, Wand2 } from 'lucide-react'
import { API_BASE_URL } from '@/lib/api'

export function UploadPage() {
  const navigate = useNavigate()
  const { uploadSkill, fetchSkills, generateSkill } = useSkillsStore()
  const [file, setFile] = useState<File | null>(null)
  const [status, setStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  // GitHub import state
  const [githubUrl, setGithubUrl] = useState('https://github.com/anthropics/skills/tree/main/skills')
  const [importResult, setImportResult] = useState<{ imported: string[], errors: any[] } | null>(null)

  // Generate from URL state
  const [genSourceUrl, setGenSourceUrl] = useState('')
  const [genSkillName, setGenSkillName] = useState('')
  const [genDescription, setGenDescription] = useState('')
  const [genStatus, setGenStatus] = useState<'idle' | 'generating' | 'success' | 'error'>('idle')
  const [genError, setGenError] = useState<string | null>(null)

  // Auto-detect source type from URL
  const genSourceType = (() => {
    const url = genSourceUrl.toLowerCase()
    if (url.includes('github.com')) return 'github' as const
    if (url.endsWith('.pdf')) return 'pdf' as const
    return 'docs' as const
  })()

  const genSourceLabel = genSourceType === 'github' ? 'GitHub Repo' : genSourceType === 'pdf' ? 'PDF Document' : 'Docs Website'

  // Auto-suggest skill name from URL
  const handleGenSourceUrlChange = (url: string) => {
    setGenSourceUrl(url)
    // Only auto-fill if user hasn't manually typed a name
    if (!genSkillName || genSkillName === prevAutoName.current) {
      let suggested = ''
      if (url.includes('github.com')) {
        // Extract "owner/repo" -> "repo" as kebab-case
        const match = url.match(/github\.com\/[^/]+\/([^/]+)/)
        if (match) suggested = match[1].toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
      } else {
        // Use hostname as fallback
        try {
          const hostname = new URL(url).hostname.replace('www.', '').split('.')[0]
          if (hostname) suggested = hostname.toLowerCase().replace(/[^a-z0-9]+/g, '-')
        } catch { /* ignore invalid URLs */ }
      }
      if (suggested) {
        setGenSkillName(suggested)
        prevAutoName.current = suggested
      }
    }
  }
  const prevAutoName = useRef('')

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const f = e.dataTransfer.files[0]
    if (f?.name.endsWith('.zip')) setFile(f)
    else setError('Please upload a .zip file')
  }, [])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) setFile(f)
  }

  const handleUpload = async () => {
    if (!file) return
    setStatus('uploading')
    setError(null)
    try {
      await uploadSkill(file)
      setStatus('success')
      setTimeout(() => navigate('/skills'), 1500)
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : 'Upload failed')
    }
  }

  const handleGitHubImport = async () => {
    setStatus('uploading')
    setError(null)
    setImportResult(null)
    try {
      const res = await fetch(`${API_BASE_URL}/admin/skills/import-github`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: githubUrl }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Import failed')
      setImportResult(data)
      setStatus('success')
      await fetchSkills()
    } catch (e) {
      setStatus('error')
      setError(e instanceof Error ? e.message : 'Import failed')
    }
  }

  const handleGenerate = async () => {
    setGenStatus('generating')
    setGenError(null)
    try {
      await generateSkill(genSourceUrl, genSourceType, genSkillName, genDescription)
      setGenStatus('success')
      setTimeout(() => navigate('/skills'), 1500)
    } catch (e) {
      setGenStatus('error')
      setGenError(e instanceof Error ? e.message : 'Generation failed')
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Add Skills</h1>

      <Tabs defaultValue="github">
        <TabsList>
          <TabsTrigger value="github"><Github className="mr-2 h-4 w-4" />Import from GitHub</TabsTrigger>
          <TabsTrigger value="upload"><Upload className="mr-2 h-4 w-4" />Upload ZIP</TabsTrigger>
          <TabsTrigger value="generate"><Wand2 className="mr-2 h-4 w-4" />Generate from URL</TabsTrigger>
        </TabsList>

        <TabsContent value="github">
          <Card>
            <CardHeader>
              <CardTitle>Import from GitHub</CardTitle>
              <CardDescription>Import skills directly from a GitHub repository</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <Input
                  placeholder="https://github.com/owner/repo/tree/branch/path"
                  value={githubUrl}
                  onChange={e => setGithubUrl(e.target.value)}
                  className="flex-1"
                />
                <Button onClick={handleGitHubImport} disabled={status === 'uploading' || !githubUrl}>
                  {status === 'uploading' ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Github className="mr-2 h-4 w-4" />}
                  Import
                </Button>
              </div>

              <p className="text-sm text-muted-foreground">
                Example: https://github.com/anthropics/skills/tree/main/skills
              </p>

              {importResult && (
                <div className="space-y-2">
                  {importResult.imported.length > 0 && (
                    <div className="flex items-start gap-2 text-green-600">
                      <CheckCircle className="h-5 w-5 mt-0.5" />
                      <div>
                        <p className="font-medium">Imported {importResult.imported.length} skills:</p>
                        <ul className="text-sm">{importResult.imported.map(s => <li key={s}>• {s}</li>)}</ul>
                      </div>
                    </div>
                  )}
                  {importResult.errors.length > 0 && (
                    <div className="flex items-start gap-2 text-destructive">
                      <XCircle className="h-5 w-5 mt-0.5" />
                      <div>
                        <p className="font-medium">Errors:</p>
                        <ul className="text-sm">{importResult.errors.map((e, i) => <li key={i}>• {e.skill}: {e.error}</li>)}</ul>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {status === 'error' && !importResult && (
                <div className="flex items-center gap-2 text-destructive">
                  <XCircle className="h-5 w-5" /> {error}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="upload">
          <Card>
            <CardHeader>
              <CardTitle>Upload Skill Package</CardTitle>
              <CardDescription>Upload a .zip file containing your skill (SKILL.md required)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div
                className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
                  dragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/25'
                }`}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
              >
                {file ? (
                  <div className="flex flex-col items-center gap-2">
                    <FileArchive className="h-12 w-12 text-primary" />
                    <p className="font-medium">{file.name}</p>
                    <p className="text-sm text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <Upload className="h-12 w-12 text-muted-foreground" />
                    <p className="text-muted-foreground">Drag and drop your skill.zip here</p>
                    <p className="text-sm text-muted-foreground">or</p>
                    <label className="cursor-pointer">
                      <span className="text-primary hover:underline">Browse files</span>
                      <input type="file" accept=".zip" className="hidden" onChange={handleFileChange} />
                    </label>
                  </div>
                )}
              </div>

              {status === 'success' && !importResult && (
                <div className="flex items-center gap-2 text-green-600">
                  <CheckCircle className="h-5 w-5" /> Skill uploaded successfully!
                </div>
              )}
              {status === 'error' && !importResult && (
                <div className="flex items-center gap-2 text-destructive">
                  <XCircle className="h-5 w-5" /> {error}
                </div>
              )}

              <div className="flex gap-2">
                <Button onClick={handleUpload} disabled={!file || status === 'uploading'}>
                  {status === 'uploading' ? 'Uploading...' : 'Upload Skill'}
                </Button>
                <Button variant="outline" onClick={() => navigate('/skills')}>Cancel</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="generate">
          <Card>
            <CardHeader>
              <CardTitle>Generate from URL</CardTitle>
              <CardDescription>Auto-generate a skill from a documentation site, GitHub repo, or PDF</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Source URL</label>
                <Input
                  placeholder="https://github.com/owner/repo, https://docs.example.com, or https://example.com/file.pdf"
                  value={genSourceUrl}
                  onChange={e => handleGenSourceUrlChange(e.target.value)}
                />
                {genSourceUrl && (
                  <p className="text-xs text-muted-foreground">
                    Detected: <span className="font-medium text-foreground">{genSourceLabel}</span>
                    {genSourceType === 'github' && ' — will clone and analyze repository'}
                    {genSourceType === 'pdf' && ' — will download and extract PDF content'}
                    {genSourceType === 'docs' && ' — will scrape documentation pages'}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Skill Name</label>
                <Input
                  placeholder="my-skill-name (kebab-case)"
                  value={genSkillName}
                  onChange={e => { setGenSkillName(e.target.value); prevAutoName.current = '' }}
                />
                <p className="text-xs text-muted-foreground">Lowercase letters, numbers, and hyphens only</p>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Description (optional)</label>
                <Input
                  placeholder="A short description of what this skill does"
                  value={genDescription}
                  onChange={e => setGenDescription(e.target.value)}
                />
              </div>

              {genStatus === 'success' && (
                <div className="flex items-center gap-2 text-green-600">
                  <CheckCircle className="h-5 w-5" /> Skill generated successfully!
                </div>
              )}
              {genStatus === 'error' && (
                <div className="flex items-center gap-2 text-destructive">
                  <XCircle className="h-5 w-5" /> {genError}
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  onClick={handleGenerate}
                  disabled={genStatus === 'generating' || !genSourceUrl || !genSkillName}
                >
                  {genStatus === 'generating' ? (
                    <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Generating...</>
                  ) : (
                    <><Wand2 className="mr-2 h-4 w-4" />Generate</>
                  )}
                </Button>
                <Button variant="outline" onClick={() => navigate('/skills')}>Cancel</Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
