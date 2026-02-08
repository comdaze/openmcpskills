import { BrowserRouter } from 'react-router'
import { Authenticator } from '@aws-amplify/ui-react'
import { AppRoutes } from '@/routes'
import { useAuth } from '@/hooks/use-auth'
import '@aws-amplify/ui-react/styles.css'

export default function App() {
  return (
    <Authenticator.Provider>
      <AuthHandler />
    </Authenticator.Provider>
  )
}

function AuthHandler() {
  // This component handles auth state sync between Amplify and our store
  useAuth()
  
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  )
}
