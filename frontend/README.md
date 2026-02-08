# SkillForge

Admin dashboard for managing Open MCP Skills - a cloud-native MCP server providing Skills as a Service.

## Tech Stack

- React 18 + TypeScript
- Vite
- Tailwind CSS + shadcn/ui
- Zustand (state management)
- Recharts (charts)
- React Router v7

## Features

- **Dashboard**: Overview with stats, charts, and top skills
- **Skills List**: Browse, search, filter, reload, and unload skills
- **Skill Detail**: View manifest, logs, versions, and rollback
- **Upload**: Drag-and-drop skill package upload
- **Settings**: Server info and health status

## Development

```bash
# Install dependencies
npm install

# Start dev server
npm run dev

# Build for production
npm run build
```

## Configuration

Create `.env` file:

```
VITE_API_BASE_URL=http://localhost:8000
```

For production, point to your deployed MCP Skills backend.

## Backend API

The dashboard connects to the MCP Skills backend admin endpoints:

- `GET /admin/skills` - List all skills
- `GET /admin/skills/{id}` - Get skill details
- `POST /admin/skills/{id}/reload` - Reload a skill
- `DELETE /admin/skills/{id}` - Unload a skill
- `POST /admin/skills/upload` - Upload skill package
- `GET /admin/skills/{id}/logs` - Get invocation logs
- `GET /admin/skills/{id}/versions` - Get version history
- `POST /admin/skills/{id}/rollback` - Rollback to version
