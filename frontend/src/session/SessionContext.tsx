import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { caseApi } from "../api";
import type { AppConfig, AuthUser } from "../api/types";

export type SessionStatus = "loading" | "authenticated" | "anonymous";

export interface SessionContextValue {
  status: SessionStatus;
  user: AuthUser | null;
  config: AppConfig | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | undefined>(undefined);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SessionStatus>("loading");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap(): Promise<void> {
      // GET /config once (F4) and GET /auth/me to restore a server session.
      const [session, appConfig] = await Promise.all([
        caseApi.getCurrentUser().catch(() => null),
        caseApi.getConfig().catch(() => null),
      ]);
      if (cancelled) return;
      setConfig(appConfig);
      setUser(session?.user ?? null);
      setStatus(session ? "authenticated" : "anonymous");
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const session = await caseApi.login(email, password);
    setUser(session.user);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      await caseApi.logout();
    } finally {
      // FE-11: clear every piece of client session state on logout so
      // switching accounts never reveals a prior user's case data. As later
      // PRs introduce per-user caches (case lists, analyses, ...), clearing
      // them belongs here too.
      setUser(null);
      setStatus("anonymous");
    }
  }, []);

  const value = useMemo<SessionContextValue>(
    () => ({ status, user, config, login, logout }),
    [status, user, config, login, logout],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used within a SessionProvider");
  return context;
}
