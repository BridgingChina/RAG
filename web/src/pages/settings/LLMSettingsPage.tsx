import { useState } from "react"
import { Link } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { TaskRoutesTab } from "@/components/settings/llm/TaskRoutesTab"
import { ProvidersTab } from "@/components/settings/llm/ProvidersTab"
import { useAuth } from "@/contexts/AuthContext"

/**
 * LLM routing admin console (Phase E).
 *
 * Two tabs:
 *   - 任务路由 — default; 7 tasks, each bound to (provider, model).
 *   - 供应商管理 — CRUD + connectivity test.
 *
 * Admin gate: the parent `AuthGuard` already short-circuits non-admin
 * sessions with a Forbidden panel. We additionally check here so a future
 * refactor that narrows `AuthGuard`'s scope (e.g., splitting per-route
 * gates) does not silently expose this page.
 */
export function Component() {
  const { user } = useAuth()
  const [tab, setTab] = useState<"tasks" | "providers">("tasks")

  if (user && user.role !== "admin") {
    return (
      <>
        <PageHeader title="LLM 路由" description="任务到供应商 / 模型的绑定" />
        <main className="p-6">
          <div className="rounded-lg border bg-muted/30 p-6">
            <h2 className="mb-2 text-base font-semibold">无权限访问</h2>
            <p className="text-sm text-muted-foreground">
              当前账号不是管理员，无法查看 LLM 路由设置。
            </p>
          </div>
        </main>
      </>
    )
  }

  return (
    <>
      <PageHeader title="LLM 路由" description="任务到供应商 / 模型的绑定">
        <Button variant="outline" size="sm" asChild>
          <Link to="/settings">返回设置</Link>
        </Button>
      </PageHeader>
      <main className="p-6">
        <Tabs
          value={tab}
          onValueChange={(v) => setTab(v as "tasks" | "providers")}
        >
          <TabsList>
            <TabsTrigger value="tasks">任务路由</TabsTrigger>
            <TabsTrigger value="providers">供应商管理</TabsTrigger>
          </TabsList>
          <TabsContent value="tasks" className="mt-4">
            <TaskRoutesTab />
          </TabsContent>
          <TabsContent value="providers" className="mt-4">
            <ProvidersTab />
          </TabsContent>
        </Tabs>
      </main>
    </>
  )
}
