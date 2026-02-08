import { useAuthenticator } from '@aws-amplify/ui-react'
import { useEffect } from 'react'
import { useAppStore } from '@/store/app-store'

export function useAuth() {
  const { authStatus, user } = useAuthenticator((context) => [context.authStatus, context.user])
  const { setUser, clearUser } = useAppStore()

  useEffect(() => {
    if (authStatus === 'authenticated' && user) {
      setUser(user)
    } else if (authStatus === 'unauthenticated') {
      clearUser()
    }
  }, [authStatus, user, setUser, clearUser])

  return { authStatus, user }
} 