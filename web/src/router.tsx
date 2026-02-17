import { createBrowserRouter } from "react-router"
import { AuthGuard } from "@/components/auth/AuthGuard"
import { DashboardLayout } from "@/components/layout/DashboardLayout"

export const router = createBrowserRouter([
  { path: "login", lazy: () => import("@/pages/LoginPage") },
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
          { path: "taxonomy", lazy: () => import("@/pages/TaxonomyPage") },
          { path: "ingest", lazy: () => import("@/pages/IngestPage") },
          { path: "ask", lazy: () => import("@/pages/AskPage") },
          { path: "settings", lazy: () => import("@/pages/SettingsPage") },
          { path: "audit-logs", lazy: () => import("@/pages/AuditLogPage") },
        ],
      },
    ],
  },
])
