import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import type { Lvl1Distribution } from "@/lib/types"

interface Props {
  data: Lvl1Distribution[]
}

export function Lvl1BarChart({ data }: Props) {
  if (data.length === 0) {
    return <p className="text-sm text-muted-foreground">暂无数据</p>
  }

  return (
    <ResponsiveContainer width="100%" height={data.length * 50 + 40}>
      <BarChart data={data} layout="vertical" margin={{ left: 80 }}>
        <XAxis type="number" />
        <YAxis type="category" dataKey="label" width={80} />
        <Tooltip />
        <Bar dataKey="count" fill="var(--chart-1)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
