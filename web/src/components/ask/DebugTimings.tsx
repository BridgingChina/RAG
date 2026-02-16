import { Badge } from "@/components/ui/badge"

export function DebugTimings({ timings }: { timings: Record<string, number> }) {
  const stages = Object.entries(timings).filter(([key]) => key !== "total")
  const total = timings.total ?? stages.reduce((a, [, b]) => a + b, 0)
  return (
    <div className="flex flex-wrap gap-2">
      {stages.map(([key, val]) => (
        <Badge key={key} variant="secondary" className="font-mono text-xs">
          {key}: {val.toFixed(3)}s
        </Badge>
      ))}
      <Badge variant="outline" className="font-mono text-xs">
        total: {total.toFixed(3)}s
      </Badge>
    </div>
  )
}
