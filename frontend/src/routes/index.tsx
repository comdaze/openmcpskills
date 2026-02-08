import { Route, Routes } from 'react-router'
import { PublicLayout } from '@/layouts/public-layout'
import { PrivateLayout } from '@/layouts/private-layout'
import { LoginPage } from '@/pages/login'
import { DashboardPage } from '@/pages/dashboard'
import { SkillsPage } from '@/pages/skills'
import { SkillDetailPage } from '@/pages/skill-detail'
import { UploadPage } from '@/pages/upload'
import { SettingsPage } from '@/pages/settings'
import { NotFoundPage } from '@/pages/not-found'

export function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route element={<PublicLayout />}>
        <Route path="/login" element={<LoginPage />} />
      </Route>

      {/* Private routes with app sidebar */}
      <Route element={<PrivateLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/skills" element={<SkillsPage />} />
        <Route path="/skills/upload" element={<UploadPage />} />
        <Route path="/skills/:id" element={<SkillDetailPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Route>

      {/* 404 page */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
