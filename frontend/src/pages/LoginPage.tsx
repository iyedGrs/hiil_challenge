import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Scales } from "@phosphor-icons/react";
import { ApiError, dataMode } from "../api";
import { FIXTURE_DEMO_PASSWORD, FIXTURE_USERS } from "../api/fixture/seed";
import { Button } from "../components/Button";
import { roleHome } from "../session/guards";
import { useSession } from "../session/SessionContext";

export function LoginPage() {
  const { status, user, login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status !== "authenticated" || !user) return;
    const from = (location.state as { from?: Location } | null)?.from;
    navigate(from ? `${from.pathname}${from.search}` : roleHome(user.role), { replace: true });
  }, [status, user, location.state, navigate]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur inattendue s'est produite. Réessayez.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-sm rounded-md border border-border bg-surface p-8 shadow-lifted">
        <span
          aria-hidden="true"
          className="flex size-10 items-center justify-center rounded-sm bg-accent-soft text-accent"
        >
          <Scales size={22} weight="fill" />
        </span>
        <h1 className="mt-4 text-xl font-semibold text-text">Connexion</h1>
        <p className="mt-1 text-sm text-text-muted">Préparation de dossiers de litige contractuel.</p>

        <form className="mt-6 flex flex-col gap-4" onSubmit={(e) => void handleSubmit(e)} noValidate>
          <div className="flex flex-col gap-1.5">
            <label htmlFor="email" className="text-sm font-medium text-text">
              Adresse e-mail
            </label>
            <input
              id="email"
              name="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="rounded-sm border border-border-control bg-surface px-3 py-2 text-base text-text transition-colors hover:border-text-muted"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="password" className="text-sm font-medium text-text">
              Mot de passe
            </label>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-describedby={error ? "login-error" : undefined}
              aria-invalid={error ? true : undefined}
              className="rounded-sm border border-border-control bg-surface px-3 py-2 text-base text-text transition-colors hover:border-text-muted"
            />
          </div>

          {error && (
            <p id="login-error" role="alert" className="rounded-sm bg-danger-bg px-3 py-2 text-sm text-danger">
              {error}
            </p>
          )}

          <Button type="submit" pending={submitting} className="mt-2 w-full">
            {submitting ? "Connexion…" : "Se connecter"}
          </Button>
        </form>

        {dataMode === "fixture" && (
          <div className="mt-6 rounded-sm bg-warning-bg px-3 py-2 text-xs text-warning">
            <p className="font-medium">Comptes de démonstration (mode fixture uniquement) :</p>
            <ul className="mt-1 list-disc pl-4">
              {FIXTURE_USERS.map((seededUser) => (
                <li key={seededUser.email}>
                  <span className="tabular">{seededUser.email}</span> · mot de passe :{" "}
                  <span className="tabular">{FIXTURE_DEMO_PASSWORD}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
