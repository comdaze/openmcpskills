# SkillForge - Admin Dashboard

## Application Overview
- **Name**: SkillForge
- **Description**: Admin dashboard for managing Open MCP Skills - a cloud-native MCP server providing Skills as a Service
- **Target Users**: Platform administrators managing Skills lifecycle
- **Primary Purpose**: Visualize, manage, and monitor Claude Skills deployed on the MCP server
- **Primary Color**: #2563eb (blue-600)

## Core Features (Prioritized)

1. **Skills Dashboard**
   - Overview cards: total skills, active skills, total invocations, error rate
   - Recent invocation activity chart
   - Top skills by invocation count
   - Success criteria: At-a-glance view of system health
   - Backend integration: GET /admin/skills, GET /admin/skills/{id}/logs

2. **Skills List & Management**
   - Table view of all skills with status, version, invocation count
   - Filter by status (active/inactive/draft/error)
   - Search by name
   - Reload single skill / reload all
   - Unload skill
   - Success criteria: Full CRUD on skills
   - Backend integration: GET/DELETE /admin/skills, POST /admin/skills/{id}/reload

3. **Skill Detail View**
   - Manifest info (name, description, author, version, tags, allowed-tools)
   - Full SKILL.md instructions (markdown rendered)
   - File listing (scripts, references, assets)
   - Invocation stats
   - Success criteria: Complete skill information in one view
   - Backend integration: GET /admin/skills/{id}, GET /admin/skills/{id}/instructions

4. **Skill Upload**
   - Drag-and-drop zip upload
   - Validation result display
   - Success criteria: Upload and validate skill packages
   - Backend integration: POST /admin/skills/upload, POST /admin/skills/validate

5. **Version Management**
   - List all versions of a skill
   - Rollback to previous version
   - Success criteria: View history and rollback
   - Backend integration: GET /admin/skills/{id}/versions, POST /admin/skills/{id}/rollback

6. **Invocation Logs**
   - Per-skill log table (time, session, method, duration, status)
   - Filter by status (success/error)
   - Success criteria: Audit trail for skill invocations
   - Backend integration: GET /admin/skills/{id}/logs

## Page List

1. **Dashboard** (`/dashboard`)
   - Purpose: System overview with key metrics and charts
   - Components: Stat cards, bar chart (invocations), table (top skills)
   - Data: Aggregated from skills list + invocation logs

2. **Skills List** (`/skills`)
   - Purpose: Browse and manage all skills
   - Components: Data table, search, filter, action buttons
   - Data: All skills with metadata

3. **Skill Detail** (`/skills/:id`)
   - Purpose: View complete skill information
   - Components: Tabs (overview, instructions, files, logs, versions)
   - Data: Single skill detail + instructions + logs + versions

4. **Upload Skill** (`/skills/upload`)
   - Purpose: Upload new skill packages
   - Components: Dropzone, validation results, progress indicator
   - Data: Upload response

5. **Settings** (`/settings`)
   - Purpose: Server configuration display
   - Components: Server info, endpoint URLs, storage backend status
   - Data: GET /info, GET /health

## Data Models

1. **Skill**
   - id, name, description, status, version, author, tags, invocation_count, last_invoked_at

2. **InvocationLog**
   - skill_id, invoked_at, session_id, method, duration_ms, status, error_message

3. **SkillVersion**
   - skill_id, version, published_at

## UI Components

1. **Dashboard Page**
   - shadcn: Card, Tabs, Badge, Table
   - Custom: StatCard, InvocationChart

2. **Skills List Page**
   - shadcn: Table, Input, Select, Button, Badge, DropdownMenu
   - Custom: SkillStatusBadge

3. **Skill Detail Page**
   - shadcn: Tabs, Card, Badge, Table, ScrollArea, Separator
   - Custom: MarkdownRenderer, FileTree

4. **Upload Page**
   - shadcn: Card, Button, Alert
   - Custom: DropzoneUpload

5. **Settings Page**
   - shadcn: Card, Separator, Badge

---

## Implementation Checklist

- [x] Generate app name (SkillForge) and project folder
- [x] Clone repo to `frontend/` folder and install dependencies
- [x] Analyze codebase structure
- [x] Update README.md with app overview and stack
- [x] Update package.json name and app references
- [x] Update app name and description on login page
- [ ] Generate favicon.png and splash.png
- [x] Create mock amplify_outputs.json
- [x] Configure API base URL to point to MCP server backend
- [x] Create Zustand store with skills data + mock data
- [x] Create Dashboard page with stat cards and charts
- [x] Create Skills List page with data table
- [x] Create Skill Detail page with tabs
- [x] Create Upload page with dropzone
- [x] Create Settings page
- [x] Add Version Management tab to Skill Detail
- [x] Add Invocation Logs tab to Skill Detail
- [x] Update sidebar navigation
- [x] Update routing
- [x] Final verification - all pages working (build passes)
