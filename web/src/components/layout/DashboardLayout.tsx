import { Outlet } from "react-router"
import { SidebarProvider } from "@/components/ui/sidebar"
import { SidebarInset } from "@/components/ui/sidebar"
import { TooltipProvider } from "@/components/ui/tooltip"
import { AppSidebar } from "./AppSidebar"

export function DashboardLayout() {
  // Read persisted sidebar state from localStorage
  const defaultOpen = localStorage.getItem("sidebar-open") !== "false"

  return (
    <TooltipProvider>
      <SidebarProvider
        defaultOpen={defaultOpen}
        onOpenChange={(open) => localStorage.setItem("sidebar-open", String(open))}
      >
        <AppSidebar />
        <SidebarInset>
          <Outlet />
        </SidebarInset>
      </SidebarProvider>
    </TooltipProvider>
  )
}
