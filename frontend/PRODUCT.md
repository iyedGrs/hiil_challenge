# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Vite + React + TypeScript (strict) + React Router + Tailwind CSS v4, hand-written accessible components (no component library). Decided by the project owner, not open for this surface.

## Users

- **Preparer** — a Tunisian business owner (MSME) or their lawyer, acting alone on a case. Describes a contract dispute, uploads supporting documents, reviews AI-assisted checks, responds to gaps, and submits a dossier for review. Not a technical user; may be working under time pressure with imperfect paperwork. Uses one shared interface regardless of whether they are the business owner or a lawyer.
- **Reviewer** — an authorized platform reviewer who receives submitted dossiers, opens the frozen snapshot, and marks it received / requests clarification / marks reviewed. Cannot edit the case.

## Product Purpose

Help a preparer assemble a contract-dispute dossier (MVP: unpaid goods invoice) before professional review: check that expected evidence exists, is readable, and is internally consistent; surface gaps as targeted findings; let the preparer respond or correct the claim; and hand a reviewed snapshot to an authorized reviewer. Success is a well-organized, honestly-labelled dossier — not a legal verdict.

## Positioning

The product distinguishes, precisely and repeatedly, between "we did not find this evidence in what you gave us" and "this claim is true." It never authenticates, never certifies, never predicts an outcome. That restraint — bounded existence/readability/consistency checks instead of a verdict — is the thing a careless competitor would blur.

## Operating Context

- French-first UI; source documents may contain Arabic text that must render in its own direction (`dir="auto"`), never forced into the surrounding LTR flow.
- Money is always a backend-supplied decimal string in TND; the UI never computes or reformats it through floating-point arithmetic.
- Fixture mode (seeded, in-memory, offline) and HTTP mode (real backend) are switched by one environment variable; fixture mode is never allowed to look like a live result.
- The preparer works through: intake → documents → analysis/findings → respond/reassess → final review → submission. The reviewer works through: inbox → immutable snapshot → event actions.
- Legal-pack coverage may be `unvalidated`; the UI must keep that visible rather than implying legal certainty.

## Capabilities and Constraints

- Supported case type at MVP: `unpaid_goods_invoice` only; currency `TND` only. Unsupported values are rejected client-side, never silently coerced to the default.
- Upload formats: PDF, JPEG, PNG. Limits (10 active files, 30 pages, 10 MiB/file, 50 MiB/case) are enforced server-side; the client only improves feedback.
- No legal rules, monetary arithmetic, or model-provider SDK code belongs in the frontend — B9 (backend.md) is authoritative for every shape and status.
- Terminology is fixed by spec and must not be softened or dramatized: document states (`uploaded`, `processing`, `ready`, `partial`, `unreadable`, `rejected`), check results (`satisfied`, `contradicted`, `unassessable`, `not_applicable`), finding status (`open`, `resolved`), job states/phases, submission language ("Transmis pour examen sur la plateforme", never "Déposé au tribunal").

## Brand Commitments

None. Out of scope per spec (`frontend.md` F7): no branding system. Visual identity is limited to design tokens (color, type, spacing, radii, motion), not a logo or brand voice system.

## Evidence on Hand

No real customer content, testimonials, or case data exists. The one demo case (20,000 TND unpaid-goods-invoice claim, per `spec/progress.md` P6) is synthetic seed data for the fixture adapter and must be visibly labelled as such everywhere it appears.

## Product Principles

1. Never let fixture/demo data read as a live AI result — the fixture banner is permanent, not a first-run tip.
2. State the limitation, not a euphemism: "not found in reviewed material" beats "missing," which beats implying fraud.
3. One interface serves both the business owner and the lawyer; no persona-switching UI.
4. Money and legal text are backend facts rendered verbatim; the UI is a faithful renderer, not a calculator or a legal voice.
5. Familiarity over flourish: this is a task tool used under stress, not a marketing surface.

## Accessibility & Inclusion

Keyboard reachability, visible focus, labels bound to inputs, errors linked via `aria-describedby`, and correct bidi handling for embedded Arabic text are explicit acceptance criteria (FE-10), not optional polish.
