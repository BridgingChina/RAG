import { createContext, useContext, useState, type ReactNode } from "react"
import type { UserInfo } from "@/lib/types"

interface AuthContextType {
  user: UserInfo | null
  setUser: (user: UserInfo | null) => void
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)

  const logout = () => {
    localStorage.removeItem("auth-token")
    setUser(null)
    window.location.href = "/login"
  }

  return (
    <AuthContext.Provider value={{ user, setUser, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used within AuthProvider")
  return ctx
}
