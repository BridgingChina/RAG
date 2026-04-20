import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react"
import { redirectToLogin, signOut, type SessionUser } from "@/lib/auth"

interface AuthContextType {
  user: SessionUser | null
  setUser: (user: SessionUser | null) => void
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null)

  const logout = useCallback(async () => {
    await signOut()
    setUser(null)
    redirectToLogin()
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
