import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"
import type { UserInfo } from "@/lib/types"

interface AuthContextType {
  user: UserInfo | null
  setUser: (user: UserInfo | null) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)

  const logout = useCallback(() => {
    localStorage.removeItem("auth-token")
    setUser(null)
    window.location.href = "/login"
  }, [])

  const value = useMemo(() => ({ user, setUser, logout }), [user, logout])

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
