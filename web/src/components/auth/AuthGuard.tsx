import { useEffect, useRef, useState } from "react"
import { Outlet } from "react-router"
import { getSession, redirectToLogin } from "@/lib/auth"
import { useAuth } from "@/contexts/AuthContext"

/**
 * Phase 2+3: the console no longer hosts a login form. Unauthenticated
 * visitors (or non-admin sessions) are sent straight to the auth Worker
 * at auth.bridgingchina.net, which handles the whole login / MFA /
 * magic-link flow and redirects them back here.
 */
export function AuthGuard() {
  const { setUser } = useAuth()
  const [checking, setChecking] = useState(true)
  const checkedRef = useRef(false)

  useEffect(() => {
    if (checkedRef.current) return
    checkedRef.current = true

    getSession()
      .then((session) => {
        if (!session) {
          redirectToLogin()
          return
        }
        if (session.user.role !== "admin") {
          // Signed-in non-admin: treat as no access, bounce to auth UI
          // so they can sign out / switch account if needed.
          redirectToLogin()
          return
        }
        setUser(session.user)
        setChecking(false)
      })
      .catch(() => {
        redirectToLogin()
      })
  }, [setUser])

  if (checking) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">验证中...</p>
      </div>
    )
  }

  return <Outlet />
}
