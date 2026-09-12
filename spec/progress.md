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
| UI-02 | Create frontend package and explicit fixture adapter | Not started | Development authorization | |
| UI-03 | Intake form and targeted follow-up experience | Not started | UI-01, UI-02 | |
| UI-04 | Upload list, limits, source-page preview | Not started | UI-01, UI-02 | |
| UI-05 | Validated findings, coverage and response controls | Not started | UI-01, UI-02 | |
| UI-06 | Job polling and reassessment changes | Not started | UI-05 | |
| UI-07 | Final review, export and submission | Not started | UI-05 | |
| UI-08 | Reviewer inbox, snapshot and clarification | Not started | UI-01, UI-02 | |
| UI-09 | HTTP adapter integration and FE-01–FE-12 checks | Not started | API contract implemented | |

UI update template: completed task, current task, exact blocked endpoint/field, evidence (commit/test/demo note), next handoff. Do not edit API status without coordination.

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
