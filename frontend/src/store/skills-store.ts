import { create } from 'zustand'
import { apiFetch, API_BASE_URL } from '@/lib/api'

export interface Skill {
  id: string
  name?: string
  description?: string
  status: 'active' | 'inactive' | 'draft' | 'error'
  version?: string
  author?: string
  tags?: string[]
  invocation_count?: number
  last_invoked_at?: string
  updated_at?: string
  manifest?: {
    name?: string
    description?: string
    license?: string
    metadata?: {
      author?: string
      version?: string
      tags?: string[]
    }
  }
}

export interface InvocationLog {
  skill_id: string
  invoked_at: string
  session_id?: string
  method: string
  duration_ms?: number
  status: 'success' | 'error'
  error_message?: string
}

export interface SkillVersion {
  skill_id: string
  version: string
  published_at: string
}

interface SkillsState {
  skills: Skill[]
  loading: boolean
  error: string | null
  fetchSkills: () => Promise<void>
  reloadSkill: (id: string) => Promise<void>
  reloadAll: () => Promise<void>
  unloadSkill: (id: string) => Promise<void>
  uploadSkill: (file: File) => Promise<void>
  getSkillLogs: (id: string) => Promise<InvocationLog[]>
  getSkillVersions: (id: string) => Promise<SkillVersion[]>
  rollbackSkill: (id: string, version: string) => Promise<void>
}

// Mock data for development
const mockSkills: Skill[] = [
  { id: 'calculator', name: 'Calculator', description: 'Basic math operations', status: 'active', version: '1', invocation_count: 42 },
  { id: 'code-review', name: 'Code Review', description: 'AI-powered code review', status: 'active', version: '1', invocation_count: 15 },
  { id: 'csv-data-summarizer-claude-skill', name: 'CSV Summarizer', description: 'Summarize CSV data', status: 'active', version: '1', invocation_count: 8 },
  { id: 'hello-world', name: 'Hello World', description: 'Simple greeting skill', status: 'active', version: '1', invocation_count: 100 },
  { id: 'web-search', name: 'Web Search', description: 'Search the web', status: 'active', version: '1', invocation_count: 25 },
]

export const useSkillsStore = create<SkillsState>((set, get) => ({
  skills: [],
  loading: false,
  error: null,

  fetchSkills: async () => {
    set({ loading: true, error: null })
    try {
      const data = await apiFetch<{ skills: Skill[] }>('/admin/skills')
      set({ skills: data.skills, loading: false })
    } catch (e) {
      // Fallback to mock data in dev
      set({ skills: mockSkills, loading: false, error: null })
    }
  },

  reloadSkill: async (id) => {
    await apiFetch(`/admin/skills/${id}/reload`, { method: 'POST' })
    await get().fetchSkills()
  },

  reloadAll: async () => {
    await apiFetch('/admin/skills/reload-all', { method: 'POST' })
    await get().fetchSkills()
  },

  unloadSkill: async (id) => {
    await apiFetch(`/admin/skills/${id}`, { method: 'DELETE' })
    await get().fetchSkills()
  },

  uploadSkill: async (file) => {
    const formData = new FormData()
    formData.append('file', file)
    await fetch(`${API_BASE_URL}/admin/skills/upload`, { method: 'POST', body: formData })
    await get().fetchSkills()
  },

  getSkillLogs: async (id) => {
    try {
      const data = await apiFetch<{ logs: InvocationLog[] }>(`/admin/skills/${id}/logs`)
      return data.logs
    } catch { return [] }
  },

  getSkillVersions: async (id) => {
    try {
      const data = await apiFetch<{ versions: SkillVersion[] }>(`/admin/skills/${id}/versions`)
      return data.versions
    } catch { return [] }
  },

  rollbackSkill: async (id, version) => {
    await apiFetch(`/admin/skills/${id}/rollback`, { method: 'POST', body: JSON.stringify({ version }) })
    await get().fetchSkills()
  },
}))
