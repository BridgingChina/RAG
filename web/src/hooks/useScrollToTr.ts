/**
 * useScrollToTr — deep-link helper for the inline translation review UX.
 *
 * Reads ``?tr=<anchor>`` from the current URL (set by the central
 * /translations page when a row is clicked) and scrolls + briefly highlights
 * the matching ``[data-tr="<anchor>"]`` element. The highlight class is
 * removed after 2 seconds.
 *
 * Use once per page; mounting the hook re-runs the effect whenever the
 * ``tr`` param changes.
 */
import { useEffect } from "react"
import { useSearchParams } from "react-router"

export function useScrollToTr() {
  const [params] = useSearchParams()
  const tr = params.get("tr")

  useEffect(() => {
    if (!tr) return
    // Defer to next paint so the cell has a chance to mount after the
    // initial useApi fetch resolves.
    const id = window.setTimeout(() => {
      const el = document.querySelector(
        `[data-tr="${CSS.escape(tr)}"]`,
      ) as HTMLElement | null
      if (!el) return
      el.scrollIntoView({ behavior: "smooth", block: "center" })
      el.classList.add("ring-highlight")
      window.setTimeout(() => el.classList.remove("ring-highlight"), 2000)
    }, 50)
    return () => window.clearTimeout(id)
  }, [tr])
}
