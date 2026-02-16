import { SidebarTrigger } from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"

interface PageHeaderProps {
  title: string
  description?: string
  children?: React.ReactNode  // action buttons slot
}

export function PageHeader({ title, description, children }: PageHeaderProps) {
  return (
    <header className="flex h-14 items-center gap-3 border-b bg-white px-6">
      <SidebarTrigger />
      <Separator orientation="vertical" className="h-5" />
      <div className="flex-1">
        <h1 className="text-sm font-medium">{title}</h1>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
      {children && <div className="flex items-center gap-2">{children}</div>}
    </header>
  )
}
