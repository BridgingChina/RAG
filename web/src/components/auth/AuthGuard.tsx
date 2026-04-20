import { useEffect, useRef, useState } from "react"
import { Outlet } from "react-router"
import { getSession, redirectToLogin, signOut, type SessionUser } from "@/lib/auth"
import { useAuth } from "@/contexts/AuthContext"
import { Button } from "@/components/ui/button"

/**
 * Phase 2+3: the console no longer hosts a login form. Unauthenticated
 * visitors are sent straight to the auth Worker at auth.bridgingchina.net.
 *
 * Signed-in-but-non-admin sessions are NOT bounced back to the login UI —
 * that used to create a redirect loop (console → login → re-auth with the
 * same non-admin cookie → console → ...). Instead we render a terminal
 * Forbidden panel with an explicit sign-out button.
 */
type GuardView = "checking" | "forbidden" | "ok"

export function AuthGuard() {
  const { setUser } = useAuth()
  const [view, setView] = useState<GuardView>("checking")
  const [deniedUser, setDeniedUser] = useState<SessionUser | null>(null)
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
          setDeniedUser(session.user)
          setView("forbidden")
          return
        }
        setUser(session.user)
        setView("ok")
      })
      .catch(() => {
        redirectToLogin()
      })
  }, [setUser])

  if (view === "checking") {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">验证中...</p>
      </div>
    )
  }

  if (view === "forbidden") {
    return <ForbiddenPanel user={deniedUser} />
  }

  return <Outlet />
}

function ForbiddenPanel({ user }: { user: SessionUser | null }) {
  const [busy, setBusy] = useState(false)

  const handleSignOut = async () => {
    setBusy(true)
    try {
      await signOut()
    } finally {
      redirectToLogin()
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-muted/30">
      <div className="w-full max-w-md rounded-lg border bg-background p-8 shadow-sm">
        <h1 className="text-xl font-semibold">无权限访问管理后台</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          当前账号 <span className="font-mono">{user?.email ?? "（未知）"}</span>{" "}
          不是管理员，无法进入 console。请退出后换用管理员账号登录，或联系管理员开通权限。
        </p>
        <div className="mt-6 flex justify-end">
          <Button onClick={handleSignOut} disabled={busy}>
            {busy ? "退出中..." : "退出登录"}
          </Button>
        </div>
      </div>
    </div>
  )
}
