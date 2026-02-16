import { createBrowserRouter } from "react-router"
import { DashboardLayout } from "@/components/layout/DashboardLayout"

export const router = createBrowserRouter([
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
      { path: "ingest", lazy: () => import("@/pages/IngestPage") },
      { path: "ask", lazy: () => import("@/pages/AskPage") },
    ],
  },
])
