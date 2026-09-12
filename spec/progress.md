# Shared progress

Baseline: v1.0 documentation split. Scope: contract-dispute document existence, readability and bounded integrity/consistency checks. Full expert replacement is excluded.

Contributors:

- **UI** — Contributor 1: frontend, API client, previews and reviewer interface.
- **API** — Contributor 2: backend, AI, checklist, source validation, arithmetic and local infrastructure.

Replace these labels with your names when assigning work. Keep one shared tracker rather than two diverging progress files.

Documents: [frontend](frontend.md), [backend and canonical contract](backend.md), [local development](local-dev.md).

## P1. Current state

- [x] Frontend specification written.
- [x] Backend specification written with user-supplied deterministic boundaries.
- [x] Canonical API contract and mock payload examples documented.
- [x] Local-development environment and future commands documented.
- [x] Shared progress and handoff plan created.
- [ ] Application implementation authorized/started.
- [ ] Frontend implemented.
- [ ] Backend/worker implemented.
- [ ] Live AI access tested.
- [ ] Legal pack reviewed by a Tunisian practitioner.
- [ ] Docker startup executed successfully.
- [ ] Integrated demo validated.

Only documentation exists from this task. Unchecked items are not claims of completed work. Future commands in local-dev.md have not been executed against an application.

## P2. Decisions to record

| ID | Decision | Current state | Owner |
| --- | --- | --- | --- |
| D01 | One preparer role for MSME/lawyer; separate reviewer | Agreed in conversation | Both |
| D02 | AI checks existence/integrity; does not replace expert investigation | Agreed in latest clarification | Both |
| D03 | Fixed checklist chooses law; model judges supplied checks | Agreed in latest constraints | API |
| D04 | Money calculated only in Decimal code; no conversion | Agreed in latest constraints | API |
| D05 | Verify all source facts before display; stable check/subject identity | Agreed in latest constraints | API |
| D06 | Initial case type `unpaid_goods_invoice`, TND | Proposed default; confirm | Both |
| D07 | React/TypeScript, FastAPI, PostgreSQL, one DB worker | Proposed implementation default; confirm | Both |
| D08 | AI provider/model and usable credit balance | Unknown; do not share keys here | API |
| D09 | Initial checklist author/reviewer and review date | Unassigned | API |
| D10 | French UI, Arabic/French sources | Proposed default; validate scan path | UI/API |
| D11 | First reviewer demo identity/remit | Choose one authorized platform reviewer; no official filing claim | Both |

These choices can be confirmed asynchronously. They do not prevent the documentation split. Do not mark a proposed choice approved without the team's decision.

## P3. UI workstream

| ID | Task | Status | Depends on | Evidence / notes |
| --- | --- | --- | --- | --- |
| UI-01 | Confirm B9 payloads, enums and error handling | Not started | Joint contract review | |
| UI-02 | Create frontend package and explicit fixture adapter | In review | Development authorization | PR `feat/ui-02-scaffold` → master, "feat(ui): scaffold frontend, CaseApi adapters and design system (UI-02)". Vite+React+TS(strict)+Router+Tailwind v4 scaffold; `PRODUCT.md`/`DESIGN.md`; `src/api/types.ts` (all B9 types, gaps below), `CaseApi` interface, fixture adapter (seeded 2 preparers + 1 reviewer, demo case per P6) and HTTP adapter; adapter selection via `VITE_DATA_MODE`; app shell (session restore, role route guards, fixture banner FE-12, header, 404); `/login` fully built, other F4 routes placeholder. `npm run typecheck/test/build/lint` all pass; browser-checked desktop+mobile. |
| UI-03 | Intake form and targeted follow-up experience | In review | UI-01, UI-02 | PR `feat/ui-03-intake` → `feat/ui-02-scaffold`, "feat(ui): cases list and structured intake with follow-up questions (UI-03)". `/cases` list (claimant/counterparty, tabular amount+currency, intake badge, revision, updated time, empty/loading/error states); `/cases/new` structured intake (case type/outcome/currency from `GET /config`, decimal-string amount validation with comma→dot only when unambiguous, four optional native date inputs, 30–4000-char narrative with counter, server `field_errors` mapped onto fields, all entered data preserved on error); shared `IntakeForm` reused by a minimal `/cases/:caseId` for follow-up answering/claim editing when intake is not ready, plus an accessible tab-bar skeleton (Documents/Vérifications/Activité/Soumission) for the ready case; fixture gate now asks "Quels biens ont été fournis ?" when the narrative never mentions goods, resolved by editing the narrative or answering the mapped follow-up, `UNSUPPORTED_CASE_TYPE` returns 422 before any case is created, and `REVISION_CONFLICT` reloads the case. `npm run typecheck/test/build` pass; `lint` see note below. |
| UI-04 | Upload list, limits, source-page preview | Not started | UI-01, UI-02 | |
| UI-05 | Validated findings, coverage and response controls | Not started | UI-01, UI-02 | |
| UI-06 | Job polling and reassessment changes | Not started | UI-05 | |
| UI-07 | Final review, export and submission | Not started | UI-05 | |
| UI-08 | Reviewer inbox, snapshot and clarification | Not started | UI-01, UI-02 | |
| UI-09 | HTTP adapter integration and FE-01–FE-12 checks | Not started | API contract implemented | |

UI update template: completed task, current task, exact blocked endpoint/field, evidence (commit/test/demo note), next handoff. Do not edit API status without coordination.

### B9 gaps (UI provisional types, pending API confirmation)

B9 (backend.md) is authoritative but does not spell out every field name or inner shape. Where a route or object was described in prose only, `frontend/src/api/types.ts` defines a minimal provisional TypeScript type (each marked `// PROVISIONAL (B9 gap): ...` in the source) consistent with B9 conventions (`{items,next_cursor}`, the error envelope, decimal strings, UTC ISO timestamps). Confirm with API before relying on these shapes past UI-02:

- `GET /config`: inner shape of `limits` (assumed `max_active_files`, `max_total_pages`, `max_file_bytes`, `max_case_bytes`, named after local-dev.md L3) and of `legal_coverage` (assumed a `case_type → "unvalidated"|"validated"` map).
- Auth: `user` object fields (assumed `id`, `email`, `role`, `display_name`).
- CSRF header name for mutating requests (assumed `X-CSRF-Token`).
- Idempotency header name for `POST /cases/{id}/analyses|exports|submissions` (assumed `Idempotency-Key`).
- Claim: `follow_up_answers` entry field names (assumed `{question_id, answer}`).
- `GET /cases` summary row fields (assumed `case_id, case_type, claimant_name, counterparty_name, claimed_amount, currency, revision, intake_status, updated_at`).
- `GET /cases/{id}` overall composition (claim/revision/documents/latest job+analysis/submissions/activity) — assumed field names `latest_job`, `latest_analysis`, `submissions`, `activity`.
- Document object fields beyond id (assumed `filename, document_type, pages, uploaded_at, state, error, active`).
- `GET /documents/{id}/pages/{page}` response shape (assumed `document_id, page, image_url, source_text, method, quality`).
- Saved finding-response object fields (assumed `finding_id, action, explanation, document_ids, created_at`).
- `reconciliation` object fields beyond "decimal strings, currency, source fact IDs, coverage qualification" (assumed `documented_balance, currency, source_fact_ids, coverage_note`).
- `Recipient`, `ExportJob`, `Submission`, `ReviewerSubmissionSummary`, `ReviewEvent`, `ReviewerSubmissionDetail` field names (all assumed from the prose description of what each screen needs, per frontend.md F4).
- Case activity-log entry shape (assumed `id, type, message, created_at`).
- `field_errors` field-name conventions for follow-up questions targeting a date: assumed either the bare key (`contract`, `delivery`, `invoice`, `payment_due`) or a dotted `dates.<key>` path both anchor to that date input; anything else renders in a generic "Informations complémentaires" section as a bounded short-answer field (UI-03).
- `follow_up_answers` semantics when a question's `field` names a real claim field (e.g. `narrative`): UI-03 treats editing that field directly as answering the question (no separate answer text is required in that case); `follow_up_answers` entries are only produced for questions whose `field` does not match a known claim field.

None of these are load-bearing for UI-02 (fixture mode only needs internal consistency); they matter once UI-09 wires the HTTP adapter to a real API.

## P4. API workstream

| ID | Task | Status | Depends on | Evidence / notes |
| --- | --- | --- | --- | --- |
| API-01 | Confirm B9 and synthetic expected outcomes with UI | Not started | Joint contract review | |
| API-02 | App/DB migrations, sessions and authorization | Not started | Development authorization | |
| API-03 | Intake schema and cheap gate | Not started | API-01, API-02 | |
| API-04 | File/page registry and OCR/text path | Not started | API-02 | |
| API-05 | Reviewed checklist/pack or explicit unvalidated coverage mode | Not started | D06, D09 | |
| API-06 | Stage 1 extraction and conservative provenance validation | Not started | API-04; D08 needed for live mode only | Fixture mode can proceed first |
| API-07 | Stage 2 supplied-check judgments and publish validation | Not started | API-05, API-06 | |
| API-08 | Decimal reconciliation and stable subject/finding identity | Not started | API-06 | |
| API-09 | Durable jobs, caching, revision and cost controls | Not started | API-02 | |
| API-10 | Exports and immutable reviewer submission | Not started | API-07–API-09 | |
| API-11 | Compose, seed accounts and actual startup guide verification | Not started | API-02 | |
| API-12 | BE-01–BE-15 and live credit-limited smoke check | Not started | API-03–API-11 | |

API is the heavier track. Keep one provider/category and finish the validated response contract early so UI can integrate. Optional intake semantic AI can be deferred; source verification and deterministic calculations cannot.

## P5. Joint handoff schedule

Times are a proposed allocation within the 24-hour hackathon, not actual progress timestamps.

| Time | UI handoff | API handoff | Integration result |
| --- | --- | --- | --- |
| Hours 0–2 | Agree screens and fixture responses | Agree B9, provider, checklist and synthetic case | Contract freeze v1 |
| Hours 2–7 | Intake/documents against fixtures | Sessions, intake and document registry | First real case and upload |
| Hours 7–13 | Findings/source viewer and response loop | Validated checks and deterministic money output | One analysed case in UI |
| Hours 13–18 | Reassessment and reviewer screens | Versioned findings, export/submission | Correction loop and handoff |
| Hours 18–22 | Integrated browser acceptance checks | Boundary tests, live model/usage check | Known limitations recorded |
| Hours 22–24 | Demo rehearsal | Startup/recovery and quota check | Three-minute end-to-end proof |

If behind, cut polish, registration, email, analytics and broader case types first. Preserve current-revision checks, provenance, permissions and explicit fixture/live labels.

## P6. Demo checklist

- [ ] Create one synthetic preparer case with a 20,000 TND claim.
- [ ] Missing delivery evidence produces a validated finding.
- [ ] Add acceptable delivery evidence and a linked 5,000 TND payment.
- [ ] Reassessment preserves finding identity and recognizes the new evidence.
- [ ] Backend calculates 15,000 TND documented balance and flags the claim discrepancy.
- [ ] User correction or disagreement is preserved without making evidence true by assertion.
- [ ] Submit a reviewed snapshot to the assigned reviewer.
- [ ] Reviewer opens the exact version, including unresolved issues if any.
- [ ] Provider failure and unreadable evidence display honestly.
- [ ] Record actual latency, token cost and sample size; no unmeasured years-saved claim.

## P7. Change and blocker log

| Entry | Contributor | Change / blocker | Resolution / next action |
| --- | --- | --- | --- |
| Spec baseline | Documentation | Created four Markdown planning files; no app code or servers | UI/API can review and assign names |
| Contract review | Documentation | Checked JSON examples, local links, revision handling and export job results | Documentation checks passed; implementation tests remain unrun |

Before changing an endpoint, enum or schema: update backend.md B9, note the change here, tell the other contributor and update UI fixtures in the same handoff. Keep secrets and real case contents out of this tracker.
