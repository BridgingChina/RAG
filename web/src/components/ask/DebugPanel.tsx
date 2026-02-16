import { useState } from "react"
import { ChevronRight } from "lucide-react"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Button } from "@/components/ui/button"
import type { DebugInfo } from "@/lib/types"
import { DebugTimings } from "./DebugTimings"
import { DebugFacet } from "./DebugFacet"
import { DebugChannel } from "./DebugChannel"

const CHANNEL_LABELS: Record<string, string> = {
  anchor: "Anchor 通道",
  concept: "Concept 通道",
  analogy: "Analogy 通道",
}

export function DebugPanel({ debug }: { debug: DebugInfo }) {
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())

  function toggle(key: string) {
    setOpenSections((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  function toggleAll() {
    const allKeys = ["timings", "facet", ...debug.channels.map((c) => c.channel)]
    if (openSections.size === allKeys.length) {
      setOpenSections(new Set())
    } else {
      setOpenSections(new Set(allKeys))
    }
  }

  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50/50 p-4 space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-600">调试信息</h3>
        <Button variant="ghost" size="sm" onClick={toggleAll} className="text-xs h-7">
          {openSections.size > 0 ? "全部折叠" : "全部展开"}
        </Button>
      </div>

      <Section title="耗时统计" id="timings" open={openSections.has("timings")} onToggle={toggle}>
        <DebugTimings timings={debug.timings} />
      </Section>

      <Section title="Facet 抽取" id="facet" open={openSections.has("facet")} onToggle={toggle}>
        <DebugFacet facet={debug.facet} />
      </Section>

      {debug.channels.map((ch) => (
        <Section
          key={ch.channel}
          title={`${CHANNEL_LABELS[ch.channel] ?? ch.channel} (${ch.final_ids.length} 条)`}
          id={ch.channel}
          open={openSections.has(ch.channel)}
          onToggle={toggle}
        >
          <DebugChannel data={ch} />
        </Section>
      ))}
    </div>
  )
}

function Section({
  title,
  id,
  open,
  onToggle,
  children,
}: {
  title: string
  id: string
  open: boolean
  onToggle: (id: string) => void
  children: React.ReactNode
}) {
  return (
    <Collapsible open={open} onOpenChange={() => onToggle(id)}>
      <CollapsibleTrigger className="flex items-center gap-1 text-sm text-slate-500 hover:text-slate-700 cursor-pointer w-full py-1">
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-90" : ""}`} />
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent className="pl-5 pt-1 pb-2">
        {children}
      </CollapsibleContent>
    </Collapsible>
  )
}
