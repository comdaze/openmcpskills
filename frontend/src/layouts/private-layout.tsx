import { ReactNode } from 'react'
import { Outlet, Navigate, useLocation } from 'react-router'
import { AppSidebar } from '@/components/app-sidebar'
import { useAppStore } from '@/store/app-store'
import { SidebarProvider, SidebarTrigger } from '@/components/ui/sidebar'
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb'
import { Separator } from '@/components/ui/separator'

interface PrivateLayoutProps {
  children?: ReactNode
}

const routeNames: Record<string, string> = {
  '/': 'Home',
  '/dashboard': 'Dashboard',
  '/skills': 'Skills',
  '/skills/upload': 'Upload',
  '/settings': 'Settings',
}

export function PrivateLayout({ children }: PrivateLayoutProps) {
  const { isAuthenticated, isLoading } = useAppStore()
  const location = useLocation()
  const pathname = location.pathname

  if (isLoading) {
    return <div className="flex h-screen items-center justify-center">Loading...</div>
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  const currentRouteName = routeNames[pathname] || pathname.split('/').pop() || 'Home'

  return (
    <SidebarProvider>
      <div className="flex h-screen w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col">
          <header className="flex h-16 shrink-0 items-center gap-2 px-6">
            <div className="flex items-center gap-2">
              <SidebarTrigger className="-ml-1" />
              <Separator orientation="vertical" className="h-4" />
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem className="hidden md:block">
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  {pathname !== '/' && (
                    <>
                      <BreadcrumbSeparator className="hidden md:block" />
                      <BreadcrumbItem>
                        <BreadcrumbPage>{currentRouteName}</BreadcrumbPage>
                      </BreadcrumbItem>
                    </>
                  )}
                </BreadcrumbList>
              </Breadcrumb>
            </div>
          </header>
          <main className="flex-1 overflow-auto p-6 w-full max-w-full">
            <div className="mx-auto w-full max-w-7xl">
              {children || <Outlet />}
            </div>
          </main>
        </div>
      </div>
    </SidebarProvider>
  )
}
