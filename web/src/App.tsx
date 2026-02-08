import { useState } from "react"
import { TabNav } from "@/components/layout/TabNav"
import { AskPanel } from "@/components/ask/AskPanel"
import { IngestPanel } from "@/components/ingest/IngestPanel"

function App() {
  const [tab, setTab] = useState("ask")

  return (
    <div className="min-h-screen bg-slate-50">
      <TabNav value={tab} onValueChange={setTab} />
      <main className="mx-auto max-w-3xl px-6 py-8">
        {tab === "ask" && <AskPanel />}
        {tab === "ingest" && <IngestPanel />}
      </main>
    </div>
  )
}

export default App
