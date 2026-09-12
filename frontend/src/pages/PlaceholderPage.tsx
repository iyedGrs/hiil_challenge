interface PlaceholderPageProps {
  title: string;
  description?: string;
}

/** Shared shell for routes a later PR builds (see spec/frontend.md F4 route table). */
export function PlaceholderPage({ title, description }: PlaceholderPageProps) {
  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-xl font-semibold text-text">{title}</h1>
      <p className="mt-2 text-sm text-text-muted">
        {description ?? "Cet écran sera construit dans une prochaine étape."}
      </p>
    </div>
  );
}
