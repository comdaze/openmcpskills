import { ReactNode } from 'react'
import { Outlet } from 'react-router'

interface PublicLayoutProps {
  children?: ReactNode
}

export function PublicLayout({ children }: PublicLayoutProps) {
  return (
    <div className="min-h-screen">
      {children || <Outlet />}
    </div>
  )
} 