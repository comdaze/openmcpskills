import { useAuthenticator } from '@aws-amplify/ui-react'
import { useEffect, useRef } from 'react'
import { useAppStore } from '@/store/app-store'

function isAuthConfigured(): boolean {
  return !!(window as any).__AMPLIFY_AUTH_CONFIGURED__
}

export function useAuth() {
  const { authStatus, user } = useAuthenticator((context) => [context.authStatus, context.user])
  const { setUser, clearUser } = useAppStore()
  const bypassApplied = useRef(false)

  useEffect(() => {
    // When Amplify auth is not configured (local dev), auto-authenticate
    if (!isAuthConfigured() && !bypassApplied.current) {
      bypassApplied.current = true
      setUser({ username: 'local-dev', userId: 'local-dev' })
    }
  }, [setUser])

  useEffect(() => {
    if (!isAuthConfigured()) return

    if (authStatus === 'authenticated' && user) {
      setUser(user)
    } else if (authStatus === 'unauthenticated') {
      clearUser()
    }
  }, [authStatus, user, setUser, clearUser])

  return { authStatus, user }
}
