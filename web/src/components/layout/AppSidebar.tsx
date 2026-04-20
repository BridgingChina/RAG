import { NavLink } from "react-router"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import {
  LayoutDashboard,
  Blocks,
  Landmark,
  FileText,
  FolderTree,
  BookOpen,
  Upload,
  MessageSquare,
  Settings,
  ScrollText,
  LogOut,
} from "lucide-react"
import { useAuth } from "@/contexts/AuthContext"

const navGroups = [
  {
    label: "概览",
    items: [
      { path: "/", icon: LayoutDashboard, label: "仪表盘" },
    ],
  },
  {
    label: "数据管理",
    items: [
      { path: "/chunks", icon: Blocks, label: "知识块" },
      { path: "/bridges", icon: Landmark, label: "桥梁" },
      { path: "/sources", icon: FileText, label: "来源" },
      { path: "/taxonomy", icon: FolderTree, label: "分类目录" },
      { path: "/knowledge-points", icon: BookOpen, label: "知识点" },
    ],
  },
  {
    label: "工具",
    items: [
      { path: "/ingest", icon: Upload, label: "入库" },
      { path: "/ask", icon: MessageSquare, label: "问答测试" },
    ],
  },
  {
    label: "系统",
    items: [
      { path: "/settings", icon: Settings, label: "设置" },
      { path: "/audit-logs", icon: ScrollText, label: "审计日志" },
    ],
  },
]

export function AppSidebar() {
  const { user, logout } = useAuth()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" className="font-medium">
              桥梁知识库
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        {navGroups.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarMenu>
              {group.items.map((item) => (
                <SidebarMenuItem key={item.path}>
                  <NavLink to={item.path} end={item.path === "/"}>
                    {({ isActive }) => (
                      <SidebarMenuButton asChild isActive={isActive}>
                        <span>
                          <item.icon />
                          <span>{item.label}</span>
                        </span>
                      </SidebarMenuButton>
                    )}
                  </NavLink>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="sm" className="text-muted-foreground">
              {user?.name || user?.email || ""}
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton size="sm" onClick={logout} className="text-muted-foreground">
              <LogOut />
              <span>退出登录</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
