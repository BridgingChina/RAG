const FACET_LABELS: Record<string, string> = {
  bridge_type: "桥型",
  material: "材料",
  era: "年代",
  region: "区域",
  function: "功能",
}

export function DebugFacet({ facet }: { facet: Record<string, unknown> | null }) {
  if (!facet) return <p className="text-sm text-muted-foreground">未提取到 facet</p>

  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
      {Object.entries(FACET_LABELS).map(([key, label]) => {
        const val = facet[key]
        const display = val == null ? "—" : Array.isArray(val) ? val.join(", ") : String(val)
        return (
          <div key={key}>
            <span className="text-muted-foreground">{label}:</span>{" "}
            <span className="font-medium">{display}</span>
          </div>
        )
      })}
    </div>
  )
}
