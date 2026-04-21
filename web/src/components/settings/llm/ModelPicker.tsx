import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useLLMProviderModels } from "@/hooks/useLLMProviderModels"
import type { ModelInfoPublic } from "@/lib/types/llm"

interface ModelPickerProps {
  providerId: string | null
  value: string | null
  onChange: (modelId: string) => void
  disabled?: boolean
  placeholder?: string
}

function formatModelLabel(m: ModelInfoPublic): string {
  if (m.context_window) {
    const kTokens = Math.round(m.context_window / 1000)
    return `${m.display_name} · ${kTokens}K`
  }
  return m.display_name
}

export function ModelPicker({
  providerId,
  value,
  onChange,
  disabled,
  placeholder,
}: ModelPickerProps) {
  const { data, loading, error } = useLLMProviderModels(providerId)

  const isDisabled = disabled || !providerId || loading

  // Build a sentinel-free value. Radix Select does not accept "" as a value.
  const selectValue = value ?? undefined

  let hint = placeholder ?? "选择模型"
  if (!providerId) {
    hint = "请先选择供应商"
  } else if (loading) {
    hint = "加载模型列表中..."
  } else if (error) {
    hint = "模型列表加载失败"
  } else if (data && data.length === 0) {
    hint = "暂无模型，请先「测试并刷新」"
  }

  return (
    <Select
      value={selectValue}
      onValueChange={onChange}
      disabled={isDisabled}
    >
      <SelectTrigger className="w-full">
        <SelectValue placeholder={hint} />
      </SelectTrigger>
      <SelectContent>
        {data && data.length > 0
          ? data.map((m) => (
              <SelectItem key={m.model_id} value={m.model_id}>
                {formatModelLabel(m)}
              </SelectItem>
            ))
          : null}
      </SelectContent>
    </Select>
  )
}
