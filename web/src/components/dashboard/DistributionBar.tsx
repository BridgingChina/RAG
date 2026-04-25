interface DistributionBarItem {
  label: string
  count: number
  color: string // Tailwind bg class or inline style — use design token classes
}

interface DistributionBarProps {
  items: DistributionBarItem[]
}

export function DistributionBar({ items }: DistributionBarProps) {
  const total = items.reduce((sum, item) => sum + item.count, 0)

  // Handle empty state
  if (total === 0) {
    return (
      <div className="space-y-3">
        <div className="h-8 w-full rounded-md bg-muted" />
        <p className="text-sm text-muted-foreground">暂无数据</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Stacked bar */}
      <div className="flex h-8 w-full overflow-hidden rounded-md">
        {items.map((item) => {
          const percentage = (item.count / total) * 100
          return (
            <div
              key={item.label}
              className={item.color}
              style={{ width: `${percentage}%` }}
            />
          )
        })}
      </div>

      {/* Labels */}
      <div className="flex flex-wrap gap-4">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-2">
            <div className={`h-3 w-3 rounded-sm ${item.color}`} />
            <span className="text-sm text-muted-foreground">
              {item.label}
            </span>
            <span className="text-sm font-medium">{item.count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
