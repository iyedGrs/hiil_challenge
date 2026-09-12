import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-md px-6 py-16 text-center">
      <h1 className="text-xl font-semibold text-text">Page introuvable</h1>
      <p className="mt-2 text-sm text-text-muted">Cette page n'existe pas ou n'est plus disponible.</p>
      <Link to="/" className="mt-4 inline-block text-sm text-accent hover:underline">
        Retour à l'accueil
      </Link>
    </div>
  );
}
