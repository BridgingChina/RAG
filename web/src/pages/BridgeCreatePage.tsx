import { useNavigate } from "react-router"
import { PageHeader } from "@/components/layout/PageHeader"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { BridgeForm } from "@/components/bridges/BridgeForm"
import { createBridge } from "@/lib/api"
import type { BridgeCreateRequest } from "@/lib/types"

export function Component() {
  const navigate = useNavigate()

  const handleCreate = async (data: BridgeCreateRequest) => {
    const bridge = await createBridge(data)
    navigate(`/bridges/${bridge.id}`)
  }

  return (
    <>
      <PageHeader title="新建桥梁">
        <Button onClick={() => navigate("/bridges")} variant="outline">
          返回
        </Button>
      </PageHeader>

      <main className="p-6">
        <Card>
          <CardHeader>
            <CardTitle>桥梁信息</CardTitle>
          </CardHeader>
          <CardContent>
            <BridgeForm onSubmit={handleCreate} submitLabel="创建桥梁" />
          </CardContent>
        </Card>
      </main>
    </>
  )
}
