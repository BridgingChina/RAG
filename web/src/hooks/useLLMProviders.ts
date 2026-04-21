import { useApi } from "@/hooks/useApi"
import { listProviders } from "@/lib/api/llm"
import type { ProviderPublic } from "@/lib/types/llm"

/**
 * Fetch the full provider list for the admin console. Filters are applied
 * client-side for now — the list is small (< 10 rows in practice) and
 * filtering on the server would force a refetch per filter change.
 */
export function useLLMProviders(params?: { enabled?: boolean }) {
  const enabledFilter = params?.enabled
  const result = useApi<ProviderPublic[]>(
    () => listProviders(enabledFilter),
    [enabledFilter],
  )
  return result
}
