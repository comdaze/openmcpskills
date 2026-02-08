import { create } from 'zustand'
import { getCurrentUser, signOut } from 'aws-amplify/auth'

interface AuthState {
  user: any | null
  isAuthenticated: boolean
  isLoading: boolean
}

interface AppState extends AuthState {
  setUser: (user: any | null) => void
  clearUser: () => void
  checkAuthStatus: () => Promise<void>
  signOut: () => Promise<void>
}

export const useAppStore = create<AppState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,

  setUser: (user) => 
    set({ user, isAuthenticated: !!user, isLoading: false }),
  
  clearUser: () => 
    set({ user: null, isAuthenticated: false, isLoading: false }),
  
  checkAuthStatus: async () => {
    try {
      const user = await getCurrentUser()
      set({ user, isAuthenticated: true, isLoading: false })
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false })
    }
  },

  signOut: async () => {
    try {
      await signOut()
      set({ user: null, isAuthenticated: false })
    } catch (error) {
      console.error('Error signing out:', error)
    }
  },
}))
