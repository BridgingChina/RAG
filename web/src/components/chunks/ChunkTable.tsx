import { useNavigate } from "react-router"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { ChunkListItem } from "@/lib/types"

interface ChunkTableProps {
  items: ChunkListItem[]
}

function getBindingStatusLabel(
  status: string,
): { label: string; variant: "default" | "secondary" | "destructive" } {
  switch (status) {
    case "primary":
      return { label: "绑定", variant: "default" }
    case "ambiguous":
      return { label: "歧义", variant: "destructive" }
    case "none":
      return { label: "未绑定", variant: "secondary" }
    default:
      return { label: status, variant: "secondary" }
  }
}

function truncateText(text: string, maxLength: number = 60) {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + "..."
}

export function ChunkTable({ items }: ChunkTableProps) {
  const navigate = useNavigate()

  if (items.length === 0) {
    return (
      <div className="flex items-center justify-center py-12">
        <p className="text-muted-foreground">暂无数据</p>
      </div>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>内容预览</TableHead>
          <TableHead>桥梁</TableHead>
          <TableHead>分类</TableHead>
          <TableHead>绑定状态</TableHead>
          <TableHead>来源</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((item) => {
          const bindingStatus = getBindingStatusLabel(item.binding_status)
          return (
            <TableRow
              key={item.id}
              onClick={() => navigate(`/chunks/${item.id}`)}
              className="cursor-pointer"
            >
              <TableCell className="max-w-md">
                {truncateText(item.content_preview)}
              </TableCell>
              <TableCell>
                {item.bridge_name || (
                  <span className="text-muted-foreground">无</span>
                )}
              </TableCell>
              <TableCell>
                {item.lvl1 || (
                  <span className="text-muted-foreground">无</span>
                )}
              </TableCell>
              <TableCell>
                <Badge variant={bindingStatus.variant}>
                  {bindingStatus.label}
                </Badge>
              </TableCell>
              <TableCell>
                {item.source_title || (
                  <span className="text-muted-foreground">未命名来源</span>
                )}
              </TableCell>
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}
