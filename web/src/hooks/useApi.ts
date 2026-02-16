import { useCallback, useEffect, useRef, useState } from "react"

interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const requestIdRef = useRef(0)

  const load = useCallback(() => {
    const id = ++requestIdRef.current
    setLoading(true)
    setError(null)
    fetcher()
      .then((result) => {
        // Only apply if this is still the latest request
        if (id === requestIdRef.current) {
          setData(result)
        }
      })
      .catch((e) => {
        if (id === requestIdRef.current) {
          setError(e instanceof Error ? e.message : String(e))
        }
      })
      .finally(() => {
        if (id === requestIdRef.current) {
          setLoading(false)
        }
      })
  }, deps) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    load()
  }, [load])

  return { data, loading, error, refetch: load }
}
