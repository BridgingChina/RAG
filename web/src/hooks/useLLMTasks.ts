import { useApi } from "@/hooks/useApi"
import { listTasks } from "@/lib/api/llm"
import type { TaskRoutePublic } from "@/lib/types/llm"

/**
 * Fetch all task routes (7 rows in Phase B/C's initial seed — see
 * `app/core/llm_tasks.py::TASK_DESCRIPTIONS`).
 */
export function useLLMTasks() {
  return useApi<TaskRoutePublic[]>(() => listTasks(), [])
}
