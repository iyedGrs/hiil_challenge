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
| UI-02 | Create frontend package and explicit fixture adapter | Merged | Development authorization | PR `feat/ui-02-scaffold` → master (PR #1, merged). Vite+React+TS(strict)+Router+Tailwind v4 scaffold; `PRODUCT.md`/`DESIGN.md`; `src/api/types.ts` (all B9 types, gaps below), `CaseApi` interface, fixture adapter (seeded 2 preparers + 1 reviewer, demo case per P6) and HTTP adapter; adapter selection via `VITE_DATA_MODE`; app shell (session restore, role route guards, fixture banner FE-12, header, 404); `/login` fully built, other F4 routes placeholder. `npm run typecheck/test/build/lint` all pass; browser-checked desktop+mobile. |
| UI-03 | Intake form and targeted follow-up experience | Merged | UI-01, UI-02 | PR `feat/ui-03-intake` → `feat/ui-02-scaffold` (PR #3, merged into `feat/ui-02-scaffold`, not `master`; carried to `master` via the UI-04 PR since #3 landed on the stale stacked base). `/cases` list (claimant/counterparty, tabular amount+currency, intake badge, revision, updated time, empty/loading/error states); `/cases/new` structured intake (case type/outcome/currency from `GET /config`, decimal-string amount validation with comma→dot only when unambiguous, four optional native date inputs, 30–4000-char narrative with counter, server `field_errors` mapped onto fields, all entered data preserved on error); shared `IntakeForm` reused by a minimal `/cases/:caseId` for follow-up answering/claim editing when intake is not ready, plus an accessible tab-bar skeleton (Documents/Vérifications/Activité/Soumission) for the ready case; fixture gate now asks "Quels biens ont été fournis ?" when the narrative never mentions goods, resolved by editing the narrative or answering the mapped follow-up, `UNSUPPORTED_CASE_TYPE` returns 422 before any case is created, and `REVISION_CONFLICT` reloads the case. `npm run typecheck/test/build` pass; `lint` see note below. |
| UI-04 | Upload list, limits, source-page preview | Merged | UI-01, UI-02 | PR `feat/ui-04-documents` → `master` (PR #4, merged; also carries UI-03's commit `7958256`, see UI-03 note above). Documents tab in `/cases/:caseId`, shown even while intake needs information (F4: draft/uploads survive an unready gate); document list (filename `dir="auto"`, document type or "Type non déterminé", pages, `uploaded_at` in fr-FR, state badge for all 6 `DocumentState`s, inline error) with "Lisible" never implying authenticity; limits summary (active files/total pages/bytes vs `GET /config` limits, MiB via `Intl.NumberFormat`); multi-file `<input>` with per-file client precheck (MIME/size/remaining count/remaining bytes) and a sequential per-file upload queue chaining `expected_revision`, statuses En attente/Envoi…/Ajouté/Doublon/Refusé; duplicate response highlights and scrolls to the existing row instead of adding one; `REVISION_CONFLICT` stops the remaining queue and reloads the case; per-document Retirer (inline confirm) and Remplacer (sequential upload-then-delete, chained revisions); source-page preview panel (prev/next bounded by known page count, image/`source_text` in a `dir="auto"` whitespace-preserving block rendered as text, method/quality, "Ouvrir l'original" via `getDocumentContentUrl` with `target="_blank" rel="noopener noreferrer"`) deep-linkable via `?tab=documents&doc=<id>&page=<n>` (`Tabs` now supports a controlled `activeId`, for UI-05 citations); fixture adapter enforces MIME/per-file/per-case/active-file limits and duplicate-by-name+size, seeds 5 demo documents covering ready/partial/unreadable(with error)/Arabic-text states. `npm run typecheck/test/build` pass (45/45 tests); `lint` see note below; browser-checked desktop + ~390px width (fixture login, upload, page preview incl. Arabic). |
| UI-05 | Validated findings, coverage and response controls | Merged | UI-01, UI-02 | PR `feat/ui-05-findings` → `master` (PR #5, merged). Vérifications tab in `/cases/:caseId` (`FindingsPanel`): analysis header (status badge ready/partial/outdated, execution_mode, checklist_version, explicit `legal_coverage` label never implying validated), coverage counts (reviewed/unreadable pages, rejected facts, open-issue count, per-result counts), no completeness percentage; `outdated` banner (`analysis.revision < case.revision`, reassessment required) and `partial` banner render before the check list so a stale/incomplete run never reads as clean (FE-04); reconciliation rendered as raw backend decimal strings (no `parseFloat`/`Number`, FE-07); honest empty state ("Aucune analyse n'a encore été exécutée…"/queued-running/failed wording from `latest_job`, no run button — out of scope, UI-06). `FindingCard` keyed by server `finding_id` (never title/position): subject label + check_id/subject_id, category (basis)/message, `finding_status`/`result`/`delta` badges, reviewed-vs-unreadable document coverage, `evidence_refs` rendered as escaped `dir="auto"` text linking via a new `onOpenDocumentPage(documentId, page)` deep link (`CaseDetailPage` sets `?tab=documents&doc=&page=`, reusing UI-04's controlled `Tabs`), legal_reference_ids as opaque ids, and the previous preparer response when one exists. `FindingResponseForm`: the four B9 actions rendered from each finding's own `actions` array, `add_evidence` document picker restricted to the case's active documents, client-side validation (≥1 document for `add_evidence`, non-empty explanation for `correct_claim`/`explain_unavailable`/`disagree`), calls `respondToFinding` with `expected_revision`, always shows "La prochaine analyse déterminera l'état de cette vérification" (FE-06 — a response never resolves a finding, verified live: responding left `finding_status` at `open` and only bumped the case revision, which then correctly flipped the analysis to `outdated`), `REVISION_CONFLICT` reloads the case and keeps the response form open for re-review; `disagree` responses stay visible via the previous-response block. Result/status filters are native labeled `<select>`s (keyboard-accessible). Fixture demo case extended with 5 findings covering every result (`satisfied` citing the seeded French and Arabic pages, the F5 `unassessable`/`EVIDENCE_NOT_FOUND` missing-delivery-evidence finding, a second `unassessable`/`SOURCE_UNREADABLE` finding on the unreadable document, a code-owned `not_applicable`, and a `contradicted`/`CONFLICT` amount-discrepancy finding) plus a `reconciliation` (P6: 15,000 TND documented vs the 20,000 TND claim); `respondToFinding` persists the response and bumps revision without touching `finding_status` (`FixtureCaseApi`/`store.ts` already kept these separate). `npm run typecheck/test/build` pass (56/56 tests, 11 new: `FindingCard.test.tsx` 7 + `FindingsPanel.test.tsx` 4, covering finding rendering by `finding_id`, the citation deep link, escaped source text, the not-resolved response flow, `REVISION_CONFLICT`, the previous-response display, the outdated banner and result filtering); `lint` see note below; browser-checked desktop + ~390px width (fixture login → Vérifications tab → citation deep link → submit a `disagree` response → revision bump + outdated banner + previous-response block, all live in the running dev server). |
| UI-06 | Job polling and reassessment changes | Merged | UI-05 | PR `feat/ui-06-jobs` → `master` (PR #6, merged). Run/reassess trigger in `FindingsPanel` ("Lancer l'analyse" on the empty state, "Relancer l'analyse" once an analysis exists, both disabled while a job is active — no double submit); calls `caseApi.startAnalysis` with `expected_revision` and a `crypto.randomUUID()` idempotency key kept across a retry of the same failed attempt, cleared on success or `REVISION_CONFLICT` (which reloads the case). New `useJobPolling` hook (`src/lib/useJobPolling.ts`): polls `GET /jobs/{id}` at 2s then 5s after 30s (spec/backend.md B9 exact cadence), stops on any terminal status or unmount (cancelled flag + cleared timer, stale responses ignored), a transport error shows a transient notice and keeps polling at the 5s cadence without ever calling the failed-callback (frontend.md F4: "A transport error stops neither the server job nor its stored progress"). New `JobProgress` component renders the six exact running phases (`reading, extracting, validating_facts, checking, validating_checks, publishing`) as a step indicator plus an `aria-live`/`role="status"` text line. `FindingsPanel` resyncs to `detail.latest_job` whenever it's queued/running and differs from the job already being polled, so reopening a case with an active job (or a job superseded elsewhere) resumes polling automatically without a dedicated mount-only code path. "Still processing" notice shown past `STILL_PROCESSING_THRESHOLD_MS` while polling continues (never a failure claim) — exact threshold not specified by spec, see B9 gap below. `FindingCard`'s existing delta badge (UI-05) now uses a dedicated `FINDING_DELTA_TONE` map instead of a fixed `"info"` tone, and `FindingsPanel` adds a "Changements depuis la dernière analyse" per-delta count summary from the published analysis's own `checks[].delta` — no client-side diffing, findings stay keyed by server `finding_id` throughout (FE-06). `FixtureCaseApi.startAnalysis` now simulates a real job: creates a `queued` job, advances it through the phases on a fixed per-tick timer, supersedes (not queues behind) any still-active job for the case on a new request (B8 "one active assessment per case"), and dedupes a retried `Idempotency-Key` to the same job/response. Reassessment (`publishReassessment`/`reassessChecks` in `FixtureCaseApi.ts`) preserves every finding's `finding_id`: the seeded missing-delivery-evidence finding (`finding_delivery_invoice_0001`) resolves once the preparer has responded `add_evidence` with a document, every other still-open finding stays `still_open`, and a new `payment_due_status` check appears once on the case's second published run to demonstrate the `new` delta after reassessment (P6 demo). `npm run typecheck/test/build` pass (69/69 tests, 13 new: `useJobPolling.test.ts` 5 — cadence 2s→5s, stop on terminal, stop on unmount, transient network error keeps polling, still-processing threshold without a failure claim; `FindingsPanel.test.tsx` +4 — run button starts a job and shows phases, restore-on-open, still-processing notice, per-delta change summary keyed correctly per finding; `FixtureCaseApi.test.ts` +4 — phase advancement, reassessment identity/delta outcomes, supersede-on-new-start, idempotency-key dedupe); `lint` unchanged pre-existing warnings only (`DocumentPreview.tsx`, `SessionContext.tsx`, `guards.tsx` — see prior notes; not touched here). Not browser-checked this pass (verified via the automated suite only). |
| UI-07 | Final review, export and submission | Merged | UI-05 | PR `feat/ui-07-submission` → `master` (PR #8, merged). |
| UI-08 | Reviewer inbox, snapshot and clarification | In review | UI-01, UI-02 | PR `feat/ui-08-reviewer-inbox` (in review). `ReviewerSubmissionsPage` (`/reviewer/submissions`): loading/empty/error states, lists only submissions assigned to the signed-in reviewer (claimant, case id, revision if available, French status badge, `submitted_at` fr-FR), each row linking to its detail page. `ReviewerSubmissionDetailPage` (`/reviewer/submissions/:submissionId`): renders the frozen `ReviewerSubmissionDetail` snapshot only — claim summary, source documents (reusing `DocumentPreview`), the analysis's coverage/legal_coverage/open-finding limitations, and every check via `FindingCard` in a new `readOnly` mode (hides `FindingResponseForm`, still shows evidence citations and the preparer's frozen response) so a reviewer can never edit evidence or rewrite findings. Actions (mark received, request clarification with a required message, mark reviewed) call `caseApi.createReviewEvent`, are disabled while posting, surface API errors inline, and append to a rendered event history; a standing note states that marking a submission received/reviewed carries no legal acceptance. An unknown or unassigned submission id renders an honest "introuvable ou non autorisé" state instead of a generic error (the fixture 404s both cases alike, never distinguishing "doesn't exist" from "not yours"). `CaseDetailPage`'s "Activité" tab (previously a placeholder) now renders `detail.activity` as a newest-first list (`dir="auto"`, fr-FR timestamps), highlighting `reviewer_clarification_requested` entries so a clarification request surfaces as a notification in the preparer's own activity feed. `FixtureCaseApi`: added a `RECIPIENT_REVIEWER_ASSIGNMENTS` map (`recipient_reviewer_demo` → `user_reviewer`, seed.ts) so `listReviewerSubmissions`/`getReviewerSubmission`/`createReviewEvent` all gate on assignment, not just role, via a shared `requireAssignedSubmission` helper (a preparer or an unassigned reviewer both get a plain 404, never a distinguishing error); `getDocumentPage` now also serves pages for documents inside an assigned submission's frozen snapshot when the caller is a reviewer, instead of only the case owner's live documents (closing the FE-09 gap where a reviewer's citation links 404'd). `npm run typecheck/test/build` pass (86/86 tests, 10 new: `ReviewerSubmissionsPage.test.tsx` 2, `ReviewerSubmissionDetailPage.test.tsx` 3, `FixtureCaseApi.test.ts` +5 covering assignment-gated access, preparer role denial, unknown-id 404, FE-09 snapshot immutability after the preparer edits the claim and uploads a new document post-submission, and the clarification event surfacing in the case's own activity log); `lint` unchanged pre-existing warnings only (`DocumentPreview.tsx`, `SessionContext.tsx`, `guards.tsx`). Not browser-checked this pass (verified via the automated suite only). |
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
- Document object `size_bytes` (UI-04): not enumerated by B9; assumed a plain byte-count number, needed to render the F3 per-case byte limit summary client-side.
- No B9 route to replace an active document in place (UI-04 "Remplacer" is implemented client-side as a chained upload-then-delete of the old document, two revision bumps instead of one); confirm whether a dedicated replace endpoint is planned.
- `GET /documents/{id}/pages/{page}` for an unreadable page: assumed the route still returns 200 with `source_text: null`, `method: null`, `quality: "illisible"` rather than an error, since the document itself (not the specific page) carries the `unreadable` state.
- `CheckFinding.subject_label` (UI-05): frontend.md F4 requires a "plain subject label" on every finding card, but B9's JSON example (and the F5 mock) only carries the opaque `check_id`/`subject_id`. Added as a required string field; the fixture adapter fills it per seeded finding.
- `CaseDetail.responses` (UI-05): frontend.md F4 requires showing "the previous preparer response" on a finding card, including after navigating away and back, but B9 has no route to list saved finding responses for a case's current working revision — only `POST /findings/{id}/responses` echoes the one it just saved, and `ReviewerSubmissionDetail.responses` is a frozen post-submission snapshot. Assumed `GET /cases/{id}` also returns every saved response for the case's still-open findings, as `responses: FindingResponse[]`.
- "Still processing" wait threshold (UI-06): frontend.md F4 says only "After a UI wait threshold, display 'Still processing'..." without naming the threshold. Added `STILL_PROCESSING_THRESHOLD_MS = 90_000` (`src/lib/useJobPolling.ts`) as a sensible provisional constant; confirm the intended value with API/UX.
- A transport error's retry cadence while polling a job (UI-06): frontend.md F4 only says a transport error "stops neither the server job nor its stored progress," not what cadence resumes polling. Assumed a fixed backoff to the 5s cadence (not the elapsed-time-based 2s/5s schedule) so a flaky connection doesn't hammer retries; confirm with API.
- Simulated job-phase timing in `FixtureCaseApi` (UI-06): B9 does not (and cannot) specify real job timing. The fixture advances one phase per fixed `PHASE_DURATION_MS` (400ms) tick purely for a demoable/testable polling UI; a real job's duration is server- and provider-controlled and unrelated to this constant.
- `ReviewerSubmissionSummary.revision` (UI-08): not enumerated by B9 ("Assigned submission summaries"); added as an optional field (degrades gracefully if a real API omits it) so the inbox can show which case revision was frozen at submission time, per frontend.md's "revision if available."
- How a recipient maps to a signed-in reviewer account (UI-08): B9 has no route describing recipient→reviewer assignment. The fixture adds a fixed `RECIPIENT_REVIEWER_ASSIGNMENTS` map (`seed.ts`) so `listReviewerSubmissions`/`getReviewerSubmission`/`createReviewEvent` only ever expose a submission to its assigned reviewer; confirm the real assignment model with API before UI-09.
- Whether "submission not found" and "submission not assigned to you" should be distinguishable (UI-08): B9 gives a single 404 `NOT_FOUND` shape; the fixture returns the identical 404 for both an unknown submission id and one assigned to a different reviewer, matching B9's own guidance to "use 404 for inaccessible case resources rather than disclosing existence."

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
