import { PieChart, Pie, Cell, Legend, ResponsiveContainer, Tooltip } from "recharts"
import type { BindingDistribution } from "@/lib/types"

// CSS custom properties resolved at runtime — must use computed style for recharts Cell fill
const COLORS = {
  primary: "var(--chart-1)",   // songci-celadon: 绑定
  ambiguous: "var(--chart-3)", // yellow-hemp: 歧义
  none: "var(--chart-4)",      // distant-mountain: 未绑定
}

const LABELS: Record<string, string> = {
  primary: "绑定",
  ambiguous: "歧义",
  none: "未绑定",
}

interface Props {
  distribution: BindingDistribution
}

export function BindingPieChart({ distribution }: Props) {
  const data = [
    { name: LABELS.primary, value: distribution.primary, key: "primary" },
    { name: LABELS.ambiguous, value: distribution.ambiguous, key: "ambiguous" },
    { name: LABELS.none, value: distribution.none, key: "none" },
  ].filter((d) => d.value > 0)

  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无数据</p>
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={50}
          outerRadius={90}
          dataKey="value"
          label={({ name, value }) => `${name}: ${value}`}
        >
          {data.map((entry) => (
            <Cell
              key={entry.key}
              fill={COLORS[entry.key as keyof typeof COLORS]}
            />
          ))}
        </Pie>
        <Tooltip />
        <Legend />
      </PieChart>
    </ResponsiveContainer>
  )
}
