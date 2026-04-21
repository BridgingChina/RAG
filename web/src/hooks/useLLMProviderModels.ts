import { useCallback, useEffect, useRef, useState } from "react"
import { listProviderModels } from "@/lib/api/llm"
import type { ModelInfoPublic } from "@/lib/types/llm"

interface UseLLMProviderModelsResult {
  data: ModelInfoPublic[] | null
  loading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Fetch the cached model list for one provider. Gated by the presence of
 * `providerId` so that a `<Select>` without a provider chosen does not
 * trigger a network call. Mirrors the `useApi` shape.
 */
export function useLLMProviderModels(
  providerId: string | null | undefined,
): UseLLMProviderModelsResult {
  const [data, setData] = useState<ModelInfoPublic[] | null>(null)
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const load = useCallback(() => {
    const id = ++requestIdRef.current
    if (!providerId) {
      setData(null)
      setLoading(false)
      setError(null)
      return
    }
    setLoading(true)
    setError(null)
    listProviderModels(providerId)
      .then((models) => {
        if (id === requestIdRef.current) setData(models)
      })
      .catch((e) => {
        if (id === requestIdRef.current) {
          setError(e instanceof Error ? e.message : String(e))
        }
      })
      .finally(() => {
        if (id === requestIdRef.current) setLoading(false)
      })
  }, [providerId])

  // Kick off (or clear) on providerId change. The effect dispatches the
  // fetch via `load()`; state updates land in promise callbacks. When
  // `providerId` is null we synchronously clear — React 19's
  // `set-state-in-effect` rule flags this, matching the same pattern the
  // project-wide `useApi` hook uses.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
  }, [load])

  return { data, loading, error, refetch: load }
}
