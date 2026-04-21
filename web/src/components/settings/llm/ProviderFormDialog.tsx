import { useEffect, useState } from "react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  createProvider,
  testProvider,
  updateProvider,
} from "@/lib/api/llm"
import type {
  ProviderKind,
  ProviderPublic,
} from "@/lib/types/llm"

const KIND_OPTIONS: { value: ProviderKind; label: string }[] = [
  { value: "zhipu", label: "智谱 (Zhipu)" },
  { value: "openai_compat", label: "OpenAI 兼容 (MiniMax / others)" },
  { value: "minimax", label: "MiniMax (native)" },
]

interface ProviderFormDialogProps {
  open: boolean
  /** null = create new; existing provider = edit. */
  initial: ProviderPublic | null
  onOpenChange: (open: boolean) => void
  onSaved: () => void
}

interface FormState {
  name: string
  kind: ProviderKind
  base_url: string
  api_key_env: string
  extra_headers: string // raw JSON textarea
  timeout_read: string // raw input -> parsed to float
  enabled: boolean
}

function defaultFormState(): FormState {
  return {
    name: "",
    kind: "openai_compat",
    base_url: "",
    api_key_env: "",
    extra_headers: "",
    timeout_read: "90",
    enabled: true,
  }
}

function formStateFromProvider(p: ProviderPublic): FormState {
  return {
    name: p.name,
    kind: p.kind,
    base_url: p.base_url,
    // SECURITY: api_key_env is write-only. When editing an existing
    // provider we do NOT prefill it — the admin can re-enter it to
    // rotate, or leave blank to keep the existing value (backend PATCH
    // omits unchanged fields).
    api_key_env: "",
    extra_headers: "",
    timeout_read: String(p.timeout_read ?? 90),
    enabled: p.enabled,
  }
}

export function ProviderFormDialog({
  open,
  initial,
  onOpenChange,
  onSaved,
}: ProviderFormDialogProps) {
  const editing = !!initial
  const [form, setForm] = useState<FormState>(defaultFormState())
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [testHint, setTestHint] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    setForm(initial ? formStateFromProvider(initial) : defaultFormState())
    setError(null)
    setTestHint(null)
  }, [open, initial])

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function parseExtraHeaders(): Record<string, string> | null {
    if (!form.extra_headers.trim()) return {}
    try {
      const parsed = JSON.parse(form.extra_headers)
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        setError("额外请求头必须是 JSON 对象")
        return null
      }
      const out: Record<string, string> = {}
      for (const [k, v] of Object.entries(parsed)) {
        if (typeof v !== "string") {
          setError(`额外请求头 "${k}" 的值必须是字符串`)
          return null
        }
        out[k] = v
      }
      return out
    } catch {
      setError("额外请求头不是合法的 JSON")
      return null
    }
  }

  async function handleSave(andTest: boolean) {
    setError(null)
    setTestHint(null)

    if (!form.name.trim()) return setError("请填写供应商名称")
    if (!form.base_url.trim()) return setError("请填写 Base URL")
    if (!editing && !form.api_key_env.trim()) {
      return setError("请填写 API Key 环境变量名")
    }
    if (form.api_key_env && !/^[A-Z][A-Z0-9_]{0,63}$/.test(form.api_key_env)) {
      return setError(
        "环境变量名必须大写开头，仅含大写字母 / 数字 / 下划线",
      )
    }
    const timeoutRead = Number(form.timeout_read)
    if (!Number.isFinite(timeoutRead) || timeoutRead < 5 || timeoutRead > 600) {
      return setError("超时时间必须在 5-600 秒之间")
    }
    const headers = parseExtraHeaders()
    if (headers === null) return // error already set

    setSaving(true)
    try {
      let providerId: string
      if (editing && initial) {
        // PATCH: only send non-empty / changed fields. api_key_env is
        // only sent if the admin typed a new value.
        const payload: Record<string, unknown> = {
          name: form.name,
          base_url: form.base_url,
          extra_headers: headers,
          enabled: form.enabled,
          timeout_read: timeoutRead,
        }
        if (form.api_key_env.trim()) {
          payload.api_key_env = form.api_key_env
        }
        const updated = await updateProvider(initial.id, payload)
        providerId = updated.id
      } else {
        const created = await createProvider({
          name: form.name,
          kind: form.kind,
          base_url: form.base_url,
          api_key_env: form.api_key_env,
          extra_headers: headers,
          enabled: form.enabled,
          timeout_read: timeoutRead,
        })
        providerId = created.id
      }

      if (andTest) {
        try {
          const t = await testProvider(providerId)
          if (t.status === "ok") {
            setTestHint(`已保存；测试通过，发现 ${t.model_count} 个模型`)
          } else {
            setTestHint(`已保存；测试失败：${t.reason ?? "未知错误"}`)
          }
        } catch (e) {
          setTestHint(
            `已保存；测试失败：${e instanceof Error ? e.message : String(e)}`,
          )
        }
      }

      onSaved()
      if (!andTest) {
        onOpenChange(false)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>
            {editing ? "编辑供应商" : "新增供应商"}
          </DialogTitle>
          <DialogDescription>
            配置 LLM 供应商的连接参数。敏感值（API Key 实际内容）保存在服务端
            环境变量中，不在此表单录入。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="provider-name">名称</Label>
            <Input
              id="provider-name"
              value={form.name}
              onChange={(e) => update("name", e.target.value)}
              placeholder="例如：Zhipu Prod"
              maxLength={64}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="provider-kind">供应商类型</Label>
            {editing ? (
              <Input
                id="provider-kind"
                value={form.kind}
                disabled
                className="font-mono"
              />
            ) : (
              <Select
                value={form.kind}
                onValueChange={(v) => update("kind", v as ProviderKind)}
              >
                <SelectTrigger id="provider-kind">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KIND_OPTIONS.map((o) => (
                    <SelectItem key={o.value} value={o.value}>
                      {o.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            {editing && (
              <p className="text-xs text-muted-foreground">
                类型创建后不可修改，如需更换请删除后重建
              </p>
            )}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="provider-base-url">Base URL</Label>
            <Input
              id="provider-base-url"
              value={form.base_url}
              onChange={(e) => update("base_url", e.target.value)}
              placeholder="https://open.bigmodel.cn/api/paas/v4"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="provider-api-key-env">
              API Key 环境变量名
            </Label>
            <Input
              id="provider-api-key-env"
              value={form.api_key_env}
              onChange={(e) =>
                update("api_key_env", e.target.value.toUpperCase())
              }
              placeholder={
                editing ? "留空则保持不变" : "例如：ZHIPU_API_KEY"
              }
              className="font-mono"
              autoComplete="off"
            />
            <p className="text-xs text-muted-foreground">
              仅工程师可见；保存后前端不再展示。实际密钥值由服务端读取
              <code className="mx-1 rounded bg-muted px-1">os.environ</code>
              中同名变量。
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="provider-extra-headers">
              额外请求头（JSON，可选）
            </Label>
            <Textarea
              id="provider-extra-headers"
              value={form.extra_headers}
              onChange={(e) => update("extra_headers", e.target.value)}
              placeholder='{"X-Team": "platform"}'
              className="font-mono text-xs"
              rows={3}
            />
            <p className="text-xs text-muted-foreground">
              敏感头（Authorization / X-Api-Key 等）会被服务端自动过滤
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="provider-timeout">读超时（秒）</Label>
              <Input
                id="provider-timeout"
                type="number"
                value={form.timeout_read}
                onChange={(e) => update("timeout_read", e.target.value)}
                min={5}
                max={600}
              />
            </div>
            <div className="space-y-1.5">
              <Label>启用</Label>
              <div className="flex h-9 items-center gap-2">
                <Switch
                  checked={form.enabled}
                  onCheckedChange={(v) => update("enabled", v)}
                />
                <span className="text-sm text-muted-foreground">
                  {form.enabled ? "已启用" : "已禁用"}
                </span>
              </div>
            </div>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
          {testHint && (
            <p className="text-sm text-muted-foreground">{testHint}</p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={saving}
          >
            取消
          </Button>
          <Button
            variant="outline"
            onClick={() => handleSave(false)}
            disabled={saving}
          >
            {saving ? "保存中..." : "保存"}
          </Button>
          <Button onClick={() => handleSave(true)} disabled={saving}>
            {saving ? "保存中..." : "保存并测试"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
