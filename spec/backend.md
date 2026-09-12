# Backend and AI specification

Status: documentation baseline v1.0. Application development has not started.

Owner: **API** (Contributor 2). Collaborator: **UI** (Contributor 1).

Related documents: [frontend specification](frontend.md), [local development](local-dev.md), [shared progress](progress.md).

## B1. Scope and hard boundaries

Prepare contract-dispute documents before professional review. Check expected item/file existence, readability, references, internal consistency and preservation of originals. Do not replace expert investigation, decide liability or damages, authenticate evidence or certify legal validity.

“Integrity” is bounded: original bytes are preserved, later byte changes are detectable, cited text is located in stored page text and defined consistency checks run. None proves the original is genuine. A hash is not an authenticity certificate; OCR is not independent confirmation of a scan's truth.

User refinements supersede earlier broad wording:

1. The model extracts source amounts; it never calculates money, predicts compensation or emits a derived balance. Decimal application code owns all monetary reconciliation and discrepancy findings. No currency conversion.
2. The model never selects legal provisions, legal packs or applicability rules. A reviewed checklist contains fixed `legal_reference_ids`, acceptable evidence definitions and application conditions. Backend code selects the pack by the confirmed enumerated case type and evaluates conditions.
3. The model judges only supplied check instances as `satisfied`, `contradicted` or `unassessable`, supported by source facts. No invented checks or model-declared legal admissibility.
4. Strict intake and a cheap gate run before expensive document assessment.
5. All model output is private and provisional until schema, source and reference validation succeed. No raw model response is streamed to UI.
6. Finding identity combines a checklist `check_id` with a backend-owned stable subject ID.

The reviewed checklist limits the model's legal task; it does not eliminate errors in factual interpretation or evidence classification. Test those separately.

## B2. Planning defaults and ownership

MVP case type: `unpaid_goods_invoice`; currency: `TND`; outcomes: `payment` and `payment_plan`. These remain proposed defaults pending team confirmation. No automatic fallback for an unsupported category. One preparer role owns cases; one reviewer role receives assigned submissions. Only one owner edits a working case in MVP.

API owns FastAPI, PostgreSQL, private files, extraction/OCR, AI provider adapter, legal-pack/checklist assets, validation, jobs, auth, exports and versioning. UI owns views and frontend fixtures. **B9 is the canonical integration contract**.

Use Python 3.11 as a planning baseline, FastAPI, Pydantic v2, SQLAlchemy/Alembic, PostgreSQL 16, pdfplumber, a PDF renderer and Tesseract for scan text. Pin tested versions during implementation. Do not choose a different major stack without updating progress decisions.

Keep one codebase with an API process and a worker process. A database job table is sufficient. No agent framework, vector database, fine-tuning, Redis or autonomous web browsing.

Provider selection remains pending the team's credits. Prior model candidate: GPT-5.6 Terra. Configure provider/model externally and implement only the selected live provider for the hackathon, plus explicit fixture mode. This documentation does not assert model access or successful testing.

## B3. Structured intake and cheap gate

### Input constraints

| Field | Rule |
| --- | --- |
| `case_type` | Exact enum; reject unsupported values before any model call |
| `claimant_name`, `counterparty_name` | Trimmed, 1–200 characters each |
| `claimed_amount` | Nonnegative canonical decimal string, maximum 12 integer digits and 3 fractional digits for TND; never a JSON float |
| `currency` | `TND` for this MVP |
| `dates` | Explicit keys `contract`, `delivery`, `invoice`, `payment_due`, each ISO date or null |
| `requested_outcome` | Exact enum |
| `narrative` | Trimmed, 30–4,000 characters; never treated as trusted instructions |
| `follow_up_answers` | At most 5 answer objects, each bounded to 1,000 characters and a server-issued question ID |

Store claim revisions. Typed claim data has `origin=user_claim` with a field path and revision; it is not a document-derived fact and must not receive fake document/page provenance.

### Gate flow

1. Deterministic schema, type, length, enum and date-format validation. Pydantic extra fields forbidden; explicitly validate date and decimal string formats rather than rely on coercion. Invalid requests return 422 with field errors, no model calls.
2. Application checks detect blank/generic descriptions, unresolved required questions and insufficient transaction description. Return `needs_information` with targeted, stable questions.
3. If semantic ambiguity remains, allow one bounded text-only intake model call using the selected provider. Input only structured claim and narrative; no documents, legal search or tools. Output is `ready` or `needs_information` plus field-targeted questions. Do not let this call select case type, law, amount or dates.
4. Limit accepted follow-up questions to five and validate question targets. Failure of this optional call yields `gate_unavailable` and a retry/manual-edit path, not an expensive pipeline launch.

Reusing an unchanged claim revision reuses its gate result. Readiness is not a merits decision. `ready` means enough information exists to attempt supported document checks.

## B4. File ingestion and source text

Limits: 10 active files, 30 total pages, 10 MiB per file, 50 MiB per case. Supported MIME types: PDF/JPEG/PNG. Enforce byte limits while reading and page/pixel/resource limits during parsing. Check content signatures, sanitize display names and use generated storage keys. Reject encrypted/unparseable files with a targeted error; do not count them as assessed.

Preserve original bytes and SHA-256; never overwrite an original or silently replace it. Adding/removing/replacing active documents increments the case revision. Submitted originals remain accessible only through authorized snapshot access.

Create a document registry and page registry before model calls. Every page has immutable stored text, method (`embedded_text` or `ocr`), image pointer if relevant, quality indicators and extraction version.

- Use embedded PDF text when usable.
- For scans, render pages with a bounded PDF renderer and use Tesseract `fra+ara+eng` as a proposed baseline. Its documented language files include French and Arabic; accuracy on this dataset is untested [S4].
- The vision model may inspect page images, but facts still need a match to stored page text before publication.
- If OCR is insufficient, mark the page `unreadable` or `partial`; request a clearer copy. Never compare model-generated text to itself and call that verification.

Store OCR quality separately from citation-match status. A quote match proves correspondence to stored text, not scan authenticity or OCR correctness.

## B5. Legal pack and checklist

Store the initial pack as versioned JSON assets loaded into the database or application at startup. No vector search is needed for the bounded pack.

Each legal reference includes ID, code/article, original text, language, source URL/page, applicable dates where established, conditions, exceptions/related references, review status, reviewer and review date. Unknown effective dates must remain unknown. No invented articles or “lawyer-reviewed” labels.

The backend maps confirmed `case_type` to a fixed pack version. Each check carries:

```json
{
  "check_id": "delivery_evidence",
  "label": "Evidence supporting receipt of goods",
  "basis": "evidence_guidance",
  "legal_reference_ids": [],
  "review_status": "draft",
  "applies_when": {"case_type": "unpaid_goods_invoice"},
  "subject_type": "invoice",
  "satisfied_by": [
    {"type": "delivery_acknowledgment", "required_links": ["parties", "transaction"]},
    {"type": "receipt_confirmation_correspondence", "required_links": ["parties", "transaction"]}
  ]
}
```

This is an illustrative evidence-guidance check, not a statutory requirement. Alternative acceptable evidence prevents a fixed filename/type checklist from rejecting equivalent proof. The checklist must encode semantic conditions, not only document labels.

Lawyer-authored `legal_reference_ids` are immutable inputs to publication. The model check schema contains **no legal-reference output field**. Any returned legal ID is an extra-field violation; backend-derived display metadata supplies the fixed references after validation. Contract requirements and evidence recommendations must not be relabelled as law.

Backend application conditions are tri-state: applies, does not apply or unknown. For unknown conditions, ask for the needed fact or mark needs review; the model does not choose a legal interpretation. The model receives only instantiated checks that are eligible for assessment. Backend may publish `not_applicable` without a model judgment.

If a validated legal pack is unavailable, disable claims of legal-requirement verification and expose `legal_coverage=unvalidated`; document existence/quality/evidence-guidance checks may still be demonstrated with a visible label.

## B6. Two-stage AI workflow

### Shared model controls

Use one configured model with two task prompts and strict JSON schemas. Models have no tools, external network actions, code execution, submission capability or authority to alter trusted checklist data. Provide case narrative and document content in explicitly delimited, untrusted blocks. Preserve instruction/data separation; delimiting alone is not treated as a security guarantee.

Do not request hidden reasoning. Require short source-based explanations and allow abstention. Do not expose provisional output, even if its JSON is valid.

### Stage 1: extract candidate facts

Input: backend-owned document/page IDs, stored page text, optional page images and extraction schema.

Output: document type, candidate parties/references/dates, literal monetary amounts, cited contract/attachment references, other evidence facts and reading issues. Monetary values are copied source strings, not generated totals.

```json
{
  "document_id": "DOC_003",
  "facts": [
    {
      "kind": "invoice_total",
      "value_text": "20 000,000",
      "currency_text": "TND",
      "document_id": "DOC_003",
      "page": 1,
      "source_text": "Total TTC : 20 000,000 TND"
    }
  ]
}
```

Backend validates every candidate and assigns stable fact IDs. Structured literal values must be anchored inside the matched quote; e.g. the numeric substring must correspond to the quoted total. Do not admit an unrelated amount with a real but irrelevant quote. Semantic roles remain subject to model/test error and user review.

Cache by owner/case scope, document hash, page-text extraction version, schema/prompt version and model configuration. Unchanged documents reuse validated facts; no global cross-customer cache.

Backend creates stable subject records: transaction, invoice, payment and referenced annex. Use explicit identifiers when unique. If identity/linkage is ambiguous, preserve an unlinked subject and request clarification. The model cannot mint authoritative subjects or merge parties/invoices.

For a contract-referenced annex, code instantiates the existing `referenced_attachment_present` checklist template using the validated reference and a persistent annex subject. This permits case-specific existence checks without allowing the model to author a new legal rule or select a provision. Ambiguous attachment identity remains a clarification question.

### Stage 2: judge supplied checks

Input: current claim revision, all readable page-tagged case text within the supported limit, validated facts, fixed checklist instances with stable subjects and user explanations. This is a bounded context, not summaries alone. Never silently truncate documents and then claim an exhaustive missing-item check.

Output: only supplied check/subject pairs, result (`satisfied`, `contradicted`, `unassessable`), reason code, cited supporting fact IDs and a short bounded explanation. New candidate facts must include full provenance and pass the same gate as Stage 1. Duplicates use existing fact IDs.

```json
{
  "checks": [
    {
      "check_id": "delivery_evidence",
      "subject_id": "invoice_0001",
      "result": "unassessable",
      "reason_code": "EVIDENCE_NOT_FOUND",
      "fact_ids": [],
      "explanation": "No receipt confirmation was found in the supplied readable material."
    }
  ],
  "monetary_facts": []
}
```

If Stage 2 emits `monetary_facts`, entries can only repeat or newly extract source amounts, each with `{document_id, page, source_text}` plus raw value/currency text. No `balance`, `damages`, `total_paid`, computed difference, arithmetic narrative or model-generated reconciliation field is accepted. This implements the user's deterministic-boundary requirement. Treat narrative monetary conclusions as invalid; use backend templates for monetary findings.

`EVIDENCE_NOT_FOUND` is a reason for `unassessable`, not a fourth judgment. It means not found in assessed material. Where a relevant unreadable page or unvalidated extraction could contain the item, publish `PARTIAL_COVERAGE`/`SOURCE_UNREADABLE` instead of an unqualified absence claim. `satisfied`/`contradicted` require matched supporting facts. Unknown/extra check pairs are rejected.

The backend computes the reviewed-document manifest from actual processing, rather than trusting a model claim to have reviewed all files.

## B7. Verification, arithmetic and publication

### Source matching

Every document-derived fact carries `{document_id, page, source_text}`. Verify the document belongs to the analysed snapshot, the page exists and the quote appears in stored page text under a versioned normalization policy.

Allowed text normalization: line-ending/whitespace collapse, documented equivalent quotation marks, conservative Unicode normalization and Arabic/Persian digit-script mapping. Preserve original text and a mapping back to source offsets where possible.

Decimal-separator normalization must be **locale-aware and conservative**. Never strip punctuation globally or make `1,000`, `1.000` and `1000` universally equivalent. Normalize a numeric token only when its locale/format is unambiguous; otherwise mark it unassessable. Preserve signs, parentheses indicating negatives, currency, units and fraction precision. Do not normalize away negation or meaningful Arabic letters.

No fuzzy quote acceptance. A failed match quarantines the fact; dependent judgments cannot be published as supported. Try at most one bounded repair or mark that check unassessable. Track source match, parsing certainty and semantic judgment separately.

### Deterministic reconciliation

Use Python `Decimal` and canonical decimal strings; PostgreSQL money values use numeric fields, never floats. Retain raw value and source. Currency is never converted. Mixed-currency or ambiguous currency cases are not reconciled.

MVP reconciliation is deliberately narrow: one invoice and explicitly linked payment/credit-note records. Codes parse source strings, avoid counting both subtotal and total, de-duplicate the same transaction appearing in a receipt and bank statement, and require explicit identifiers or preparer-confirmed mapping. A matching amount alone does not establish that two records refer to the same payment.

Compute `documented_balance = invoice_total - linked_payments - linked_credit_notes` only when all inputs and links are unambiguous. Do not assume an absent receipt proves zero payments: label the result “balance based on uploaded records.” If links or signs are uncertain, publish an unresolved reconciliation check. The claimed amount comes from structured user input, not model output.

Generate discrepancy messages in code when the claimed amount differs from the documented balance. Preserve negative balances as possible overpayment/credit, not zero. Do not calculate penalties, interest, tax corrections, damages or payment-plan terms in MVP. Do not silently round excess precision.

### Stable identity and coverage

Store findings uniquely by `(case_id, check_id, subject_id)`; IDs are generated by backend code, not model text or array position. Subject records persist through case revisions and same-subject replacements. If a subject changes or is removed, retain history and mark its check not applicable; do not call it resolved by evidence. Preserve user responses with their original finding/version.

Publish a run atomically after validation. States: `ready`, `partial`, `outdated`; job failures are separate. Invalid output does not become an empty success. Backend publication includes model/prompt/checklist versions, revision, coverage and disclosure flags.

A run uses an immutable input snapshot. If the working case changes during processing, retain the historical run but set job `superseded` and analysis `outdated`. It cannot finalize a newer revision.

## B8. Persistence, jobs and permissions

| Entity | Important fields |
| --- | --- |
| User/session | Role, hashed credentials, session expiry |
| Case/ClaimRevision | Owner, canonical structured claim, revision, intake state |
| Document/Page | Immutable storage key, hash, active membership, page text/method/quality |
| Extraction/Fact | Provenance, normalization/extraction/model version, verification state |
| Subject | Stable backend ID, type, confirmed identifiers and linkage |
| LegalPack/Checklist | Version, review status, conditions, fixed references |
| Analysis/CheckResult | Input snapshot, coverage, statuses, validated results |
| Finding/FindingResponse | Stable check/subject key, history and preparer response |
| Submission/ReviewEvent | Recipient, immutable manifest, reviewed run, review state, clarification |
| Job/Usage | Lease, attempts, model calls, usage, result IDs and sanitized errors |

Use server sessions with HttpOnly cookies and server-side authorization on every case, file, page, job, export and submission route. Same-origin Vite proxy in local development; CSRF protection for state-changing requests. The server assigns roles and reviewer recipients; no privileged client role flag or shared role-switcher in integrated mode.

Create one durable DB job per revision/idempotency key. Claim jobs with a lease/heartbeat and bounded attempts. Reuse completed extraction on retry. A crash after a provider response can create uncertain billing; record attempts and avoid unbounded automatic replays. Enforce one active assessment per case.

Rate/cost controls: one concurrent provider call by default, per-request token limits, one automatic retry for retryable faults, per-run attempt budget and a configured demo spending ceiling. Reserve a conservative run allowance before dispatch and reconcile usage afterward; usage logging alone is not a hard cap.

## B9. Canonical API contract v1

Prefix `/api`. IDs are opaque strings; pages are 1-based; amounts are decimal strings; timestamps UTC ISO 8601; document dates ISO dates or null. Success objects are direct JSON, lists use `{items, next_cursor}`. Unknown fields/enum values are rejected.

Errors have `{error: {code, message, field_errors, retryable}}`. `field_errors` is an array of `{field, message}`. Never return provider raw traces or document contents in errors.

### Routes

| Method and route | Contract |
| --- | --- |
| GET `/config` | `{case_types, currencies, requested_outcomes, limits, legal_coverage, execution_mode}` |
| POST `/auth/login` | `{email,password}` -> session cookie and `{user,csrf_token}` |
| GET `/auth/me` | Current `{user,csrf_token}` |
| POST `/auth/logout` | Clear session, 204 |
| GET `/cases` | Authorized case summaries |
| POST `/cases` | Structured claim -> 201 `{case_id,revision,intake}` |
| GET `/cases/{id}` | Claim, current revision, documents, latest analysis/job, submission summaries and activity |
| PATCH `/cases/{id}/claim` | `{expected_revision,claim}` -> new revision and intake |
| POST `/cases/{id}/intake-check` | `{expected_revision}` -> intake result; cached for unchanged claim |
| POST `/cases/{id}/documents` | Multipart `file`, `expected_revision` -> 201 document and revision |
| DELETE `/cases/{id}/documents/{document_id}` | `expected_revision` query -> new revision; detach active file only |
| GET `/documents/{id}/content` | Authorized original bytes, inline/download safe headers |
| GET `/documents/{id}/pages/{page}` | Authorized page preview and source text/quality metadata |
| POST `/cases/{id}/analyses` | `{expected_revision}` + idempotency header -> 202 `{job_id,case_id,revision}` |
| GET `/jobs/{id}` | `{id,status,phase,error,result_analysis_id,result_export_id}`; phase/error/result IDs nullable |
| GET `/analyses/{id}` | Published analysis object below; pending has 409 `ANALYSIS_NOT_PUBLISHED` |
| POST `/findings/{id}/responses` | `{expected_revision,action,explanation,document_ids}` -> saved response and revision |
| GET `/recipients` | Available authorized reviewer destinations; no arbitrary email submission |
| POST `/cases/{id}/exports` | `{expected_revision,analysis_id,acknowledge_unresolved}` + idempotency header -> 202 `{job_id,export_id}` |
| GET `/exports/{id}/content` | Authorized completed package bytes |
| POST `/cases/{id}/submissions` | `{expected_revision,analysis_id,recipient_id,acknowledge_unresolved}` + idempotency header -> 201 submission |
| GET `/reviewer/submissions` | Assigned submission summaries |
| GET `/reviewer/submissions/{id}` | Immutable snapshot, documents, validated checks and events |
| POST `/reviewer/submissions/{id}/events` | `{event_type,message}`; received, clarification_requested or reviewed |
| GET `/health/live` | API process alive; no paid provider call |
| GET `/health/ready` | DB/schema/storage usable; no paid provider call |

File upload checks enforce limits before provider calls. Exact duplicate upload returns 200 `{duplicate:true,document,revision}` without a new active file/revision. Normal upload returns `{duplicate:false,document,revision}`. Scope duplicate lookup to this authorized case.

Case creation takes the following direct claim shape. The same object is nested under `claim` for PATCH. All date keys are explicit; null means not known. This is a synthetic example, not legal guidance.

```json
{
  "case_type": "unpaid_goods_invoice",
  "claimant_name": "Demo Supplier",
  "counterparty_name": "Demo Customer",
  "claimed_amount": "20000.000",
  "currency": "TND",
  "dates": {
    "contract": "2026-06-01",
    "delivery": "2026-06-10",
    "invoice": "2026-06-10",
    "payment_due": "2026-07-10"
  },
  "requested_outcome": "payment",
  "narrative": "We supplied office furniture and claim that the invoice remains unpaid.",
  "follow_up_answers": []
}
```

Mutations that change claim/evidence/responses return the updated `revision`. Multi-file upload is sequential in MVP so each request uses the most recently returned revision. A future batch endpoint can optimize this without weakening optimistic concurrency.

Intake object:

```json
{
  "status": "needs_information",
  "questions": [
    {"id": "describe_goods", "field": "narrative", "message": "Quels biens ont été fournis ?"}
  ]
}
```

Intake statuses: `not_checked`, `ready`, `needs_information`, `gate_unavailable`. A valid draft can be saved while `needs_information`. Analysis with a non-ready gate returns 409 `INTAKE_NOT_READY` plus the saved questions in `field_errors`; UI renders targeted follow-up, not pipeline failure.

Job statuses: `queued`, `running`, `succeeded`, `failed`, `superseded`. Phases: `reading`, `extracting`, `validating_facts`, `checking`, `validating_checks`, `publishing`. Export jobs use `packaging`.

Published analysis object:

```json
{
  "analysis_id": "RUN_002",
  "case_id": "CASE_001",
  "revision": 3,
  "status": "ready",
  "execution_mode": "fixture",
  "checklist_version": "tn-goods-v1",
  "legal_coverage": "unvalidated",
  "coverage": {"reviewed_pages": 4, "unreadable_pages": 0, "rejected_facts": 0},
  "checks": [
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
  ],
  "reconciliation": null
}
```

`evidence_refs` entries include `{fact_id,document_id,page,source_text}`. `reconciliation`, when available, is backend-generated and contains decimal strings, currency, source fact IDs and a coverage qualification. No raw candidate facts or model legal IDs are published.

Result enum: model's three outcomes plus code-owned `not_applicable`. Reason codes include `EVIDENCE_FOUND`, `EVIDENCE_NOT_FOUND`, `CONFLICT`, `SOURCE_UNREADABLE`, `PARTIAL_COVERAGE`, `AMBIGUOUS_LINK`, `LEGAL_COVERAGE_UNAVAILABLE`, `INVALID_SOURCE`, `NOT_APPLICABLE`. Finding status: `open`/`resolved` or null when no issue ever existed. Delta: `new`, `resolved`, `still_open`, `reopened`, `not_applicable` or null.

Error codes include `UNSUPPORTED_CASE_TYPE` (422), `INVALID_INPUT` (422), `FILE_LIMIT` (413), `UNSUPPORTED_FILE` (415), `REVISION_CONFLICT` (409), `INTAKE_NOT_READY` (409), `ANALYSIS_NOT_PUBLISHED` (409), `ANALYSIS_OUTDATED` (409), `ANALYSIS_ALREADY_RUNNING` (409), `BUDGET_EXHAUSTED` (429), `PROVIDER_UNAVAILABLE` (503). Use 401 when unauthenticated and 404 for inaccessible case resources to avoid disclosing existence.

On revisions, reject stale expected revisions atomically. Do not use client timestamps as version checks. Both contributors must agree changes here before changing fixtures or endpoints.

## B10. Export and reviewer handoff

A current published assessment is required for an assessed package. `partial` is allowed only with explicit acknowledgement and all limitations included. `failed`/unvalidated model responses cannot be submitted as assessed. `legal_coverage=unvalidated` remains prominently disclosed even in an otherwise ready analysis.

Create one ZIP with summary PDF, evidence index, checks/unresolved items, originals and a manifest. Use backend templates and stored validated facts; no extra free-form AI drafting call. Mark claim allegations, user explanations and documentary facts distinctly. Fixed references originate in the checklist, not model text.

Submission transaction freezes claim revision, document hashes/IDs, checklist version, published run, preparer responses, recipient and timestamp. Record no new fee claims or legal guarantees. Explicit submission is the only path to reviewer access. Received/reviewed statuses do not indicate legal acceptance.

Clarification requests create events. The preparer edits the working revision, reassesses and submits a new version. Reviewer access to one submission does not grant access to drafts or other cases. File detach must not destroy a submitted version; real deletion/retention policy is a pre-pilot design item.

## B11. Acceptance criteria and metrics

| ID | Backend acceptance check |
| --- | --- |
| BE-01 | Unsupported type/invalid structured input makes zero model calls. |
| BE-02 | Under-specified claim returns targeted questions and preserves draft. |
| BE-03 | Missing supported item is found; acceptable alternative evidence can satisfy the check. |
| BE-04 | Every published document fact has validated in-case page/quote provenance. |
| BE-05 | Unknown legal IDs, unknown check/subject IDs and unsupported result fields are rejected. |
| BE-06 | Arabic digit/whitespace/quote variants match conservatively; ambiguous decimal formats do not. |
| BE-07 | Model-derived balances are rejected; Decimal code handles 20,000 less 5,000 as 15,000 TND. |
| BE-08 | A receipt and statement for the same payment are not counted twice; uncertain links stay unassessable. |
| BE-09 | Partial OCR or missing coverage is not published as a definitive absence/clean dossier. |
| BE-10 | Reassessment preserves check/subject identity; removed subjects are not falsely resolved. |
| BE-11 | Unchanged files reuse extraction; revision changes make in-flight results outdated. |
| BE-12 | Preparer/reviewer boundaries hold for all file/job/export/submission routes. |
| BE-13 | Provider/schema failures cannot become empty success; retries and costs are bounded. |
| BE-14 | Explicit unresolved submission works and remains immutable after edits. |
| BE-15 | Injected instructions in narrative/documents do not change schema, access, checks or legal pack. |

Collect small-fixture check accuracy, false missing-item findings, citation failures, latency, tokens/cost, cache hits and time to complete the correction loop. Report sample size and synthetic nature. Do not infer years saved or national legal accuracy from the demo.

## B12. Work order

1. Agree B9 and synthetic fixtures with UI. Obtain provider access and a checklist review path.
2. Build persistence, sessions, strict intake and cheap gate.
3. Build file/page registry, extraction and source validation.
4. Build constrained check assessment, deterministic money checks and publication.
5. Build reassessment identity, exports and immutable reviewer handoff.
6. Run targeted BE tests and integrated demo.

The API workstream is heavier than UI. Protect time by keeping one category, one provider, one worker and seeded accounts. If behind, drop optional semantic intake AI in favor of structured follow-up rules before cutting provenance or deterministic boundaries.

## B13. Technical reference notes

- [S1: Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/) — validate output/input types; strict mode still requires explicit domain validation.
- [S2: FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/) — separate container startup and application lifecycle concerns.
- [S3: Docker Compose readiness](https://docs.docker.com/compose/how-tos/startup-order/) — a running database container is not necessarily ready; configure health checks.
- [S4: Tesseract language data](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html) — install the language data used by the scan path.

These are implementation references, not evidence that this prototype is already built or validated. No legal article was authored or certified as part of this spec split.
