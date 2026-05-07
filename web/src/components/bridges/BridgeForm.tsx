import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useApi } from "@/hooks/useApi"
import { fetchFacets } from "@/lib/api"
import type { BridgeCreateRequest, BridgeDetail } from "@/lib/types"

interface BridgeFormProps {
  initialData?: BridgeDetail
  onSubmit: (data: BridgeCreateRequest) => Promise<void>
  submitLabel: string
}

// Sentinel value for "unset" — Radix Select rejects empty string as value
const NONE = "__none__"

export function BridgeForm({
  initialData,
  onSubmit,
  submitLabel,
}: BridgeFormProps) {
  const [form, setForm] = useState<BridgeCreateRequest>({
    name: initialData?.name || "",
    aliases: initialData?.aliases || null,
    bridge_type: initialData?.bridge_type || null,
    material: initialData?.material || null,
    era: initialData?.era || null,
    region: initialData?.region || null,
    latitude: initialData?.latitude ?? null,
    longitude: initialData?.longitude ?? null,
    function: initialData?.function || null,
    summary: initialData?.summary || null,
  })

  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { data: facets } = useApi(fetchFacets, [])
  const bridgeTypes = facets?.bridge_types ?? []
  const materials = facets?.materials ?? []
  const eras = facets?.eras ?? []
  const functions = facets?.functions ?? []

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) {
      setError("名称不能为空")
      return
    }

    setIsSubmitting(true)
    setError(null)
    try {
      await onSubmit(form)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        {/* Name - Required */}
        <div className="space-y-2">
          <label className="text-sm font-medium">
            名称 <span className="text-destructive">*</span>
          </label>
          <Input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="桥梁名称"
            required
          />
        </div>

        {/* Aliases */}
        <div className="space-y-2">
          <label className="text-sm font-medium">别名</label>
          <Input
            value={form.aliases || ""}
            onChange={(e) =>
              setForm({ ...form, aliases: e.target.value || null })
            }
            placeholder="用逗号分隔多个别名"
          />
        </div>

        {/* Bridge Type */}
        <div className="space-y-2">
          <label className="text-sm font-medium">桥型</label>
          <Select
            value={form.bridge_type || NONE}
            onValueChange={(v) =>
              setForm({ ...form, bridge_type: v === NONE ? null : v })
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="选择桥型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>无</SelectItem>
              {bridgeTypes.map((type) => (
                <SelectItem key={type} value={type}>
                  {type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Material */}
        <div className="space-y-2">
          <label className="text-sm font-medium">材料</label>
          <Select
            value={form.material || NONE}
            onValueChange={(v) =>
              setForm({ ...form, material: v === NONE ? null : v })
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="选择材料" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>无</SelectItem>
              {materials.map((material) => (
                <SelectItem key={material} value={material}>
                  {material}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Era */}
        <div className="space-y-2">
          <label className="text-sm font-medium">年代</label>
          <Select
            value={form.era || NONE}
            onValueChange={(v) =>
              setForm({ ...form, era: v === NONE ? null : v })
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="选择年代" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>无</SelectItem>
              {eras.map((era) => (
                <SelectItem key={era} value={era}>
                  {era}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Region */}
        <div className="space-y-2">
          <label className="text-sm font-medium">区域</label>
          <Input
            value={form.region || ""}
            onChange={(e) =>
              setForm({ ...form, region: e.target.value || null })
            }
            placeholder="地理区域"
          />
        </div>

        {/* Latitude */}
        <div className="space-y-2">
          <label className="text-sm font-medium">纬度</label>
          <Input
            type="number"
            step="any"
            value={form.latitude ?? ""}
            onChange={(e) =>
              setForm({ ...form, latitude: e.target.value ? Number(e.target.value) : null })
            }
            placeholder="例如: 30.2741"
          />
        </div>

        {/* Longitude */}
        <div className="space-y-2">
          <label className="text-sm font-medium">经度</label>
          <Input
            type="number"
            step="any"
            value={form.longitude ?? ""}
            onChange={(e) =>
              setForm({ ...form, longitude: e.target.value ? Number(e.target.value) : null })
            }
            placeholder="例如: 120.1551"
          />
        </div>

        {/* Function */}
        <div className="space-y-2">
          <label className="text-sm font-medium">功能</label>
          <Select
            value={form.function || NONE}
            onValueChange={(v) =>
              setForm({ ...form, function: v === NONE ? null : v })
            }
          >
            <SelectTrigger>
              <SelectValue placeholder="选择功能" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>无</SelectItem>
              {functions.map((func) => (
                <SelectItem key={func} value={func}>
                  {func}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Summary - Full Width */}
        <div className="space-y-2 md:col-span-2">
          <label className="text-sm font-medium">简介</label>
          <textarea
            value={form.summary || ""}
            onChange={(e) =>
              setForm({ ...form, summary: e.target.value || null })
            }
            placeholder="桥梁简介"
            className="flex min-h-[120px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          />
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? "提交中..." : submitLabel}
      </Button>
    </form>
  )
}
