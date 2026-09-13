import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Scales, SignOut } from "@phosphor-icons/react";
import { useSession } from "../session/SessionContext";
import { roleHome } from "../session/guards";
import { Button } from "./Button";

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
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-4 border-b border-border bg-surface/95 px-6 backdrop-blur-sm">
      <Link
        to={roleHome(user.role)}
        className="inline-flex items-center gap-2 text-md font-semibold text-text no-underline transition-colors hover:text-accent"
      >
        <span
          aria-hidden="true"
          className="flex size-7 items-center justify-center rounded-sm bg-accent-soft text-accent"
        >
          <Scales size={17} weight="fill" />
        </span>
        Préparation de dossier
      </Link>
      <div className="flex items-center gap-3 text-sm">
        <span className="hidden text-text-muted sm:inline">
          {user.display_name} · {user.role === "reviewer" ? "Relecteur" : "Préparateur"}
        </span>
        <Button
          variant="secondary"
          size="sm"
          icon={<SignOut size={15} />}
          onClick={() => void handleLogout()}
          disabled={loggingOut}
        >
          {loggingOut ? "Déconnexion…" : "Se déconnecter"}
        </Button>
      </div>
    </header>
  );
}
