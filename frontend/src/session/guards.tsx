import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import type { UserRole } from "../api/types";
import { useSession } from "./SessionContext";

function FullPageStatus({ message }: { message: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas text-sm text-text-muted">{message}</div>
  );
}

function roleHome(role: UserRole): string {
  return role === "reviewer" ? "/reviewer/submissions" : "/cases";
}

/** Redirects to /login when there is no restored/active session. */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const location = useLocation();

  if (status === "loading") return <FullPageStatus message="Chargement…" />;
  if (status === "anonymous") return <Navigate to="/login" state={{ from: location }} replace />;
  return <>{children}</>;
}

/** Restricts a route to one server-returned role; wrong role is sent to their own home, never a 403 page. */
export function RequireRole({ role, children }: { role: UserRole; children: ReactNode }) {
  const { user } = useSession();
  if (!user) return null;
  if (user.role !== role) return <Navigate to={roleHome(user.role)} replace />;
  return <>{children}</>;
}

export { roleHome };
