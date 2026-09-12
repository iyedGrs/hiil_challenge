import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSession } from "../session/SessionContext";
import { roleHome } from "../session/guards";

export function AppHeader() {
  const { user, logout } = useSession();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);

  if (!user) return null;

  async function handleLogout(): Promise<void> {
    setLoggingOut(true);
    try {
      await logout();
    } finally {
      setLoggingOut(false);
      navigate("/login", { replace: true });
    }
  }

  return (
    <header className="flex items-center justify-between gap-4 border-b border-border bg-surface px-6 py-3">
      <Link to={roleHome(user.role)} className="text-md font-semibold text-text no-underline">
        Préparation de dossier
      </Link>
      <div className="flex items-center gap-4 text-sm">
        <span className="text-text-muted">
          {user.display_name} · {user.role === "reviewer" ? "Relecteur" : "Préparateur"}
        </span>
        <button
          type="button"
          onClick={() => void handleLogout()}
          disabled={loggingOut}
          className="rounded-sm border border-border-strong px-3 py-1.5 text-text transition-colors hover:bg-surface-muted disabled:opacity-50"
        >
          {loggingOut ? "Déconnexion…" : "Se déconnecter"}
        </button>
      </div>
    </header>
  );
}
