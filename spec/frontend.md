# Frontend specification

Status: documentation baseline v1.0. Application development has not started.

Owner: **UI** (Contributor 1). Collaborator: **API** (Contributor 2).

Related documents: [backend specification](backend.md), [local development](local-dev.md), [shared progress](progress.md).

## F1. Product and scope

Build the interface for a Tunisian contract-dispute document-preparation SaaS. A business owner or lawyer uses one role, `preparer`, to describe a dispute, upload documents, identify evidence gaps, respond and reassess. A separate `reviewer` receives a submitted dossier version.

The AI checks expected item existence, readability and consistency against a controlled checklist. It does not replace an expert's technical investigation, decide liability, estimate compensation, authenticate signatures or certify evidence as genuine. Monetary reconciliation and legal-reference attachment belong to backend code.

The product must distinguish:

- An expected file or referenced annex was not found in the material reviewed.
- A file exists but cannot be read or its content is inconsistent.
- A checklist item appears supported by cited information.
- An item cannot be assessed and needs clarification or professional review.

“Integrity” means these bounded checks and preservation of the uploaded original. Never show “authentic,” “legally valid,” “expert-approved,” “court-approved” or a probability of winning based on AI output.

The government is not involved in preparation. Back-office receipt is receipt in this application, not official judicial filing.

## F2. Two-person ownership

UI owns React/TypeScript views, navigation, accessibility, API client, frontend fixtures, source previews and browser verification. API owns schemas, all permissions, legal check selection, AI calls, validation, calculations, persistence, exports and submission snapshots.

The **B9 contract in backend.md is authoritative** for request fields, statuses, response shapes, errors and routes. UI may use mock data matching that contract while API builds. No production legal rules, money calculation or model-provider SDK belongs in the frontend.

Use a single `CaseApi` adapter boundary. Future fixture and HTTP implementations must expose the same methods. Fixture mode is visibly labelled “Demo data — no live analysis.” Never present a seeded response as a live AI result.

UI can work before API is finished once both contributors confirm B9 and the examples in this file.

## F3. Defaults and limits

These are planning defaults, not newly confirmed product decisions:

| Item | Default |
| --- | --- |
| Supported case type | `unpaid_goods_invoice` only |
| Requested outcomes | `payment`, `payment_plan` |
| First interface | French; preserve Arabic document text with correct direction |
| Currency | `TND` for MVP; no conversion |
| Upload formats | PDF, JPEG, PNG |
| Limits | 10 active files, 30 total pages, 10 MiB per file, 50 MiB per active case |
| Authentication | Seeded preparer/reviewer accounts, real server sessions in integrated mode |
| Collaboration | One owner per case; no shared-account assumption |

Fetch limits, enums and legal-coverage availability from `GET /api/config`. Client checks improve feedback; the server enforces all limits. Do not accept unknown case types locally and silently fall back to the default.

## F4. Routes and screens

| Route | Purpose |
| --- | --- |
| `/login` | Sign in and restore server session |
| `/cases` | List current user's cases |
| `/cases/new` | Structured intake |
| `/cases/:caseId` | Case workspace with Documents, Checks, Activity and Submit tabs |
| `/reviewer/submissions` | Assigned submission inbox |
| `/reviewer/submissions/:submissionId` | Immutable dossier and review actions |

Avoid a different interface for MSMEs and lawyers. The case stores business parties separately from account identity.

### Structured intake

Fields: case type, claimant business name, counterparty name, claimed amount, currency, contract date if known, delivery date if known, invoice date if known, payment due date if known, requested outcome and a bounded narrative. Unknown dates remain explicitly null rather than fabricated.

Names are 1–200 characters after trimming. Narrative is 30–4,000 characters; the backend also checks whether the description is meaningful. Amount is entered as a decimal string, never converted through JavaScript floating-point arithmetic. French comma input may be converted to a canonical dot only when unambiguous; otherwise ask for clarification.

The intake gate can return targeted questions, for example “What goods were supplied?” or “Which payment remains disputed?” Show each question next to its mapped input or as a short answer field. Persist answers through the claim-revision endpoint. Do not show an under-specified claim as “AI analysis failed.”

If intake requires more information, keep the draft and uploaded files. The expensive assessment cannot start until the gate is ready.

### Document workspace

Show filename, server document type, pages, upload time, reading state and errors. Upload progress is separate from analysis progress. Preview originals through authorized endpoints, with Arabic text in `dir="auto"` containers. Escape all document text; do not render uploaded HTML.

Required states: uploaded, processing, ready, partial, unreadable and rejected. Do not imply that `ready` means authentic. A duplicate is identified by the server; show the existing document instead of silently adding a second copy.

The preparer can remove an active document or upload a replacement. Removal increments the working revision and leaves previously submitted snapshots unchanged. No automatic analysis on each file selection: use the explicit action button.

Upload selected files sequentially using the latest server-returned revision, because each successful upload changes the case. Do not dispatch multiple revision-checked uploads in parallel and hide their conflicts. A duplicate does not increment the revision.

### Analysis and findings

Only render backend-published analysis responses. Never render streamed model text, unvalidated extraction or intermediate model reasoning.

Job states: `queued`, `running`, `succeeded`, `failed`, `superseded`. Running phases: `reading`, `extracting`, `validating_facts`, `checking`, `validating_checks`, `publishing`.

Poll every 2 seconds initially, then every 5 seconds after 30 seconds. Stop on terminal states or when leaving the view. A transport error stops neither the server job nor its stored progress. Reopening the case restores the active job. After a UI wait threshold, display “Still processing” with retry-status controls; do not claim server failure from a browser timeout.

Show check counts, assessment coverage and open issues. Avoid completeness percentages. If a result is partial, explain which files/checks could not be assessed. If it is outdated, show a clear banner and require reassessment before finalizing a new submission.

Each finding card includes:

- Server-owned stable `finding_id`, `check_id`, `subject_id` and plain subject label.
- Category, explanatory message and `open` or `resolved` status.
- Assessment result: `satisfied`, `contradicted`, `unassessable` or `not_applicable` (the last is set by code).
- Coverage: what files/pages were reviewed and what could not be reviewed.
- Cited source passages linked to the original page.
- Source basis: checklist, contract, claim or deterministic file/amount check.
- Backend-attached legal reference and pack validation label, when applicable.
- Suggested next action and previous preparer response.

Use neutral copy such as “Evidence not found in the reviewed material” and “The amount differs from the documented records.” Do not imply fraud or concealment.

If normalized text offsets are unavailable, open the cited page and show the matched quote beside it. Do not invent a bounding box or place an approximate highlight as if exact.

### Respond and reassess

Actions: `add_evidence`, `correct_claim`, `explain_unavailable`, `disagree`.

A response does not make a finding resolved. The next validated assessment determines its current state. User disagreement remains visible in the case history and submission. For an upload response, attach document IDs already owned by the case.

The backend supplies the change set: `new`, `resolved`, `still_open`, `reopened`, `not_applicable`. The frontend must not match findings by generated title or array position.

### Final review and submission

Display the latest revision, validated analysis coverage, claim summary, evidence index, unresolved findings and preparer explanations. `ready_for_review` is a workflow state, not a legal certificate.

Require explicit confirmation of the dossier version and chosen available recipient. Submit with `expected_revision` and an idempotency key. If the server reports a changed revision, reload and ask the user to review again.

An explicitly acknowledged partial assessment can be submitted with disclosures if the backend allows it. A failed or unvalidated run cannot be presented as an assessed dossier. Missing documents are not an endless compulsory-upload gate.

The downloadable package is produced by the backend. Show actual states: generating, ready, failed. After submission, display submission ID, version, recipient and timestamp. Use “Transmis pour examen sur la plateforme,” not “Déposé au tribunal.”

### Reviewer back office

Only list submissions assigned to the signed-in reviewer. Open the submitted snapshot, not the current working case. Show source documents, validated checks, limitations and user responses.

Actions: mark received, request clarification, mark reviewed. A request creates an event and a notification in the preparer's case activity. The preparer revises the working case and sends a new version; the reviewer cannot directly edit evidence or rewrite findings.

No government API, case scheduling, mediation negotiation or payment screen is in this build.

## F5. Contract examples for mocks

All mock responses use B9. The following is a backend-published check, not raw model JSON. The example contains no invented legal article.

```json
{
  "check_id": "delivery_evidence",
  "subject_id": "invoice_0001",
  "finding_id": "finding_delivery_invoice_0001",
  "result": "unassessable",
  "reason_code": "EVIDENCE_NOT_FOUND",
  "finding_status": "open",
  "delta": "new",
  "basis": "checklist",
  "message": "Aucune preuve de réception trouvée dans les pièces examinées.",
  "evidence_refs": [],
  "reviewed_document_ids": ["DOC_001", "DOC_002"],
  "legal_reference_ids": [],
  "actions": ["add_evidence", "explain_unavailable", "disagree"]
}
```

The complete mock set must include: intake questions, initial missing evidence, wrong-period upload, correct evidence, code-generated amount discrepancy, unreadable page, unknown date, provider failure, stale revision, unresolved submission, reviewer clarification and access denied. Fixtures stay internally consistent across navigation and reassessment.

## F6. Implementation acceptance criteria

| ID | UI acceptance check |
| --- | --- |
| FE-01 | One preparer UI serves both business owners and lawyers. |
| FE-02 | Unsupported intake values cannot start analysis; field errors and follow-ups preserve entered data. |
| FE-03 | Upload, unreadable, duplicate and limit states are distinguishable. |
| FE-04 | Only published checks are shown; partial/stale/failed runs never appear as a clean dossier. |
| FE-05 | Every displayed source opens the correct authorized document page. |
| FE-06 | Responding does not auto-resolve a finding; reassessment shows stable changes. |
| FE-07 | Money is displayed from backend strings; the UI does not calculate a balance. |
| FE-08 | Submission requires explicit review and retains unresolved issues. |
| FE-09 | Reviewer sees the received version even after working-case edits. |
| FE-10 | Keyboard navigation, readable errors and Arabic source text work on the demo viewport. |
| FE-11 | Logout clears client state; account switching does not reveal prior case data. |
| FE-12 | Fixture mode is visible and can be changed to HTTP through one configuration switch. |

## F7. Work order and handoff

1. Agree B9, fixtures, page labels and legal-coverage labels with API.
2. Build intake and document workspace against fixtures.
3. Build check cards, page preview and response loop.
4. Build final review and reviewer inbox.
5. Connect real API and complete FE acceptance checks.
6. Rehearse the integrated three-minute demo.

Update only the UI workstream in [progress.md](progress.md), except jointly owned decision and integration entries. The first integration target is a validated synthetic case appearing in the findings view; do not wait for all screens to be finished.

Out of scope: branding system, billing, self-service registration, mobile app, live chat, legal chatbot, dashboards with invented savings, expert replacement and physical defect valuation.
