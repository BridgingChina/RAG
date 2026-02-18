import { useEffect, useRef, useState } from "react"
import { Outlet, useNavigate } from "react-router"
import { fetchMe } from "@/lib/api"
import { useAuth } from "@/contexts/AuthContext"

export function AuthGuard() {
  const navigate = useNavigate()
  const { setUser } = useAuth()
  const [checking, setChecking] = useState(true)
  const checkedRef = useRef(false)

  useEffect(() => {
    if (checkedRef.current) return
    checkedRef.current = true

    const token = localStorage.getItem("auth-token")
    if (!token) {
      navigate("/login", { replace: true })
      return
    }
    fetchMe()
      .then((user) => {
        setUser(user)
        setChecking(false)
      })
      .catch(() => {
        localStorage.removeItem("auth-token")
        navigate("/login", { replace: true })
      })
  }, [navigate, setUser])

  if (checking) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">验证中...</p>
      </div>
    )
  }

  return <Outlet />
}
