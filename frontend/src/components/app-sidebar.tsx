"use client"

import * as React from "react"
import { useLocation, useNavigate } from 'react-router'
import {
  ChevronsUpDown,
  LogOut,
  LayoutDashboard,
  Boxes,
  Upload,
  Settings,
  Sparkles,
} from "lucide-react"

import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar"
import { useAppStore } from "@/store/app-store"
import { useAuth } from "@/hooks/use-auth"

const navItems = [
  { title: "Dashboard", url: "/dashboard", icon: LayoutDashboard },
  { title: "Skills", url: "/skills", icon: Boxes },
  { title: "Upload", url: "/skills/upload", icon: Upload },
  { title: "Settings", url: "/settings", icon: Settings },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const location = useLocation()
  const navigate = useNavigate()
  const { isMobile } = useSidebar()
  const { user, signOut } = useAppStore()
  const { authStatus } = useAuth()
  const [version, setVersion] = React.useState('v1.0.0')
  
  const isAuthenticated = authStatus === 'authenticated' && user

  React.useEffect(() => {
    fetch('/api/info')
      .then(r => r.json())
      .then(data => setVersion(`v${data.version}`))
      .catch(() => {})
  }, [])

  return (
    <Sidebar collapsible="icon" className="[&_[data-sidebar=sidebar]]:bg-slate-50 [&_[data-sidebar=sidebar]]:shadow-[inset_-4px_0_12px_-1px_rgba(0,0,0,0.05)]" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" onClick={() => navigate('/dashboard')}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-blue-600 text-white">
                <Sparkles className="size-4" />
              </div>
              <div className="flex flex-col gap-0.5 leading-none">
                <span className="font-semibold">SkillForge</span>
                <span className="text-xs">{version}</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            {navItems.map((item) => (
              <SidebarMenuItem key={item.title}>
                <SidebarMenuButton
                  tooltip={item.title}
                  isActive={location.pathname === item.url || (item.url === '/skills' && location.pathname.startsWith('/skills/'))}
                  onClick={() => navigate(item.url)}
                >
                  <item.icon />
                  <span>{item.title}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton size="lg" className="data-[state=open]:bg-sidebar-accent">
                  <Avatar className="h-8 w-8 rounded-lg">
                    <AvatarFallback className="rounded-lg">{isAuthenticated ? user?.username?.charAt(0)?.toUpperCase() || "A" : "A"}</AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-semibold">{isAuthenticated ? user?.username || "Admin" : "Admin"}</span>
                    <span className="truncate text-xs">{isAuthenticated ? (user?.signInDetails?.loginId || user?.userId || "admin@local") : "admin@local"}</span>
                  </div>
                  <ChevronsUpDown className="ml-auto size-4" />
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-56 rounded-lg" side={isMobile ? "bottom" : "right"} align="end" sideOffset={4}>
                <DropdownMenuLabel className="font-normal">
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-medium">{isAuthenticated ? user?.username || "Admin" : "Admin"}</p>
                    <p className="text-xs text-muted-foreground">{isAuthenticated ? (user?.signInDetails?.loginId || user?.userId || "admin@local") : "admin@local"}</p>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={signOut}>
                  <LogOut className="mr-2 h-4 w-4" />
                  {isAuthenticated ? "Log out" : "Sign in"}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  )
}
