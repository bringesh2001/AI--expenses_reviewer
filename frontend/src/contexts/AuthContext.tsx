import { createContext, useContext, ReactNode } from "react";

interface AuthCtx {
  user: { id: string; email: string } | null;
}

const AuthContext = createContext<AuthCtx>({ user: { id: "dev-user", email: "dev@northwindlogistics.com" } });

export function AuthProvider({ children }: { children: ReactNode }) {
  return (
    <AuthContext.Provider value={{ user: { id: "dev-user", email: "dev@northwindlogistics.com" } }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
