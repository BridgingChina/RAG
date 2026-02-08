import { useState } from "react"
import { TabNav } from "@/components/layout/TabNav"

function App() {
  const [tab, setTab] = useState("ask")

  return (
    <div className="min-h-screen bg-slate-50">
      <TabNav value={tab} onValueChange={setTab} />
      <main className="mx-auto max-w-3xl px-6 py-8">
        {tab === "ask" && <div className="text-slate-500">问答页（待实现）</div>}
        {tab === "ingest" && <div className="text-slate-500">入库页（待实现）</div>}
      </main>
    </div>
  )
}

export default App
