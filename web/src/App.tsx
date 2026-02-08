import { useState } from "react"
import { TabNav } from "@/components/layout/TabNav"
import { AskPanel } from "@/components/ask/AskPanel"

function App() {
  const [tab, setTab] = useState("ask")

  return (
    <div className="min-h-screen bg-slate-50">
      <TabNav value={tab} onValueChange={setTab} />
      <main className="mx-auto max-w-3xl px-6 py-8">
        {tab === "ask" && <AskPanel />}
        {tab === "ingest" && <div className="text-slate-500">入库页（待实现）</div>}
      </main>
    </div>
  )
}

export default App
