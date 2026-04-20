import { createBrowserRouter } from "react-router"
import { AuthGuard } from "@/components/auth/AuthGuard"
import { DashboardLayout } from "@/components/layout/DashboardLayout"

export const router = createBrowserRouter([
  {
    element: <AuthGuard />,
    children: [
      {
        element: <DashboardLayout />,
        children: [
          { index: true, lazy: () => import("@/pages/DashboardPage") },
          { path: "chunks", lazy: () => import("@/pages/ChunkListPage") },
          { path: "chunks/:id", lazy: () => import("@/pages/ChunkDetailPage") },
          { path: "bridges", lazy: () => import("@/pages/BridgeListPage") },
          { path: "bridges/new", lazy: () => import("@/pages/BridgeCreatePage") },
          { path: "bridges/:id", lazy: () => import("@/pages/BridgeDetailPage") },
          { path: "sources", lazy: () => import("@/pages/SourceListPage") },
          { path: "sources/:id", lazy: () => import("@/pages/SourceDetailPage") },
          { path: "sources/:sourceId/chunks/edit", lazy: () => import("@/pages/ChunkEditorPage") },
          { path: "taxonomy", lazy: () => import("@/pages/TaxonomyPage") },
          { path: "knowledge-points", lazy: () => import("@/pages/KnowledgePointListPage") },
          { path: "knowledge-points/:id", lazy: () => import("@/pages/KnowledgePointDetailPage") },
          { path: "ingest", lazy: () => import("@/pages/IngestPage") },
          { path: "ingest-tasks/:id", lazy: () => import("@/pages/IngestTaskDetailPage") },
          { path: "ask", lazy: () => import("@/pages/AskPage") },
          { path: "settings", lazy: () => import("@/pages/SettingsPage") },
          { path: "audit-logs", lazy: () => import("@/pages/AuditLogPage") },
        ],
      },
    ],
  },
])
