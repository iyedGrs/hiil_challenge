# Frontend

Vite + React + TypeScript (strict) + React Router + Tailwind CSS v4. See `../spec/frontend.md` (spec), `PRODUCT.md` and `DESIGN.md` (durable design context) before adding a screen.

## Run

```bash
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Set `VITE_DATA_MODE` in a local `.env` (copy `.env.example`) to switch adapters:

- `fixture` (default) — in-memory seeded data, no backend required. Seeded accounts are documented on the login screen.
- `http` — talks to a real backend at relative `/api`. The dev server proxies `/api` to `API_PROXY_TARGET` (default `http://127.0.0.1:8000`), preserving the prefix.

## Scripts

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite dev server |
| `npm run build` | Typecheck (`tsc -b`) then production build |
| `npm run typecheck` | Typecheck only |
| `npm test -- --run` | Run the Vitest suite once |
| `npm run lint` | Oxlint |

## Layout

- `src/api/` — `CaseApi` interface (one method per B9 route), `fixture/` and `http/` adapters, `types.ts` (B9 types; gaps marked `PROVISIONAL` and logged in `spec/progress.md`).
- `src/session/` — session context (login/logout/restore) and role route guards.
- `src/routes/`, `src/pages/`, `src/components/` — app shell and screens.
