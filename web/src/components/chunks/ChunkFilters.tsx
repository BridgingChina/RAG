import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useApi } from "@/hooks/useApi"
import { fetchTaxonomyTree } from "@/lib/api"

interface ChunkFiltersProps {
  filters: {
    search?: string
    lvl1?: string
    binding_status?: string
  }
  onChange: (filters: ChunkFiltersProps["filters"]) => void
}

export function ChunkFilters({ filters, onChange }: ChunkFiltersProps) {
  const { data: taxTree } = useApi(fetchTaxonomyTree, [])
  const lvl1Options = taxTree?.items ?? []

  return (
    <div className="flex flex-wrap items-center gap-3">
      <Input
        placeholder="搜索知识块..."
        value={filters.search || ""}
        onChange={(e) =>
          onChange({ ...filters, search: e.target.value || undefined })
        }
        className="max-w-xs"
      />

      <Select
        value={filters.lvl1 || "__all__"}
        onValueChange={(value) =>
          onChange({ ...filters, lvl1: value === "__all__" ? undefined : value })
        }
      >
        <SelectTrigger>
          <SelectValue placeholder="分类" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__all__">全部</SelectItem>
          {lvl1Options.map((item) => (
            <SelectItem key={item.node_id} value={item.label}>
              {item.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={filters.binding_status || "__all__"}
        onValueChange={(value) =>
          onChange({ ...filters, binding_status: value === "__all__" ? undefined : value })
        }
      >
        <SelectTrigger>
          <SelectValue placeholder="绑定状态" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__all__">全部</SelectItem>
          <SelectItem value="primary">绑定</SelectItem>
          <SelectItem value="ambiguous">歧义</SelectItem>
          <SelectItem value="none">未绑定</SelectItem>
        </SelectContent>
      </Select>
    </div>
  )
}
