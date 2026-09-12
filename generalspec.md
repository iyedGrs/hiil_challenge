# Full product and technical specification

Version: 1.0 consolidated planning baseline  
Date: 2026-09-12  
Delivery scope: documentation only. No application implementation or server deployment is included.

## How to use this specification

This is a standalone consolidation of the frontend, backend/AI, local-development and two-person delivery specifications. It incorporates the latest clarification: **the AI checks document and evidence existence and bounded integrity; it does not replace the expert reviewer's entire job.**

The detailed sections retain their F, B, L and P identifiers so the two contributors can coordinate with the existing split documents. Section **B9** contains the canonical API contract. Keep that contract synchronized with [backend.md](backend.md) if implementation changes it. [progress.md](progress.md) remains the live work tracker; the progress section here records the planning baseline.

### Contents

- [Product, value and MVP decisions](#product-value-and-mvp-decisions)
- [Frontend specification](#frontend-specification)
- [Backend and AI specification](#backend-and-ai-specification)
- [Local development specification](#local-development-specification)
- [Two-person delivery and progress baseline](#two-person-delivery-and-progress-baseline)

## Product, value and MVP decisions

### The product in simple English

A business owner or their lawyer describes a commercial contract dispute and uploads the available papers. The software checks the documents against a controlled evidence checklist and the references inside those documents. It shows what appears to be missing, unreadable or inconsistent, with an explanation tied to the submitted material.

The user can add evidence, correct the claim, explain why something is unavailable or disagree. A new assessment checks the updated case and preserves the history. When the user chooses to share it, the application creates a versioned dossier for a reviewer in a simple back office.

The central promise is: **find document problems while the business can still fix them, before handing the dossier to a professional reviewer.** A useful result is an actionable evidence gap with a source and a correction path, not a long generic AI report.

### Customer and business value

The initial customer is a Tunisian MSME preparing a contract-dispute dossier, either directly or through its lawyer. Both use the same `preparer` role and workflow. This does not mean they share credentials or automatically have access to each other's cases. The MVP assigns one owner to each case.

The commercial hypothesis is that earlier detection of missing or unusable evidence reduces avoidable document-chasing, repeated preparation and reviewer requests. The prototype should demonstrate that loop. It cannot establish that the product shortens court proceedings by years, eliminates expert fees or guarantees a settlement.

| Question | Planning answer |
| --- | --- |
| Who receives immediate value? | The preparer who needs to know what to collect or fix before handing over a dossier. |
| Who can buy first? | A business purchasing a case assessment or a lawyer preparing several client dossiers. |
| Why use AI? | Evidence can appear in differently named files and passages, and acceptable support can take more than one form. AI helps read and relate that content to fixed checks. |
| Why not just upload files to a chatbot? | The workflow validates citations, preserves finding identity, tracks corrections and produces a reproducible dossier version. |
| Proposed charging hypothesis | A case bundle with a bounded number of reassessments; a later subscription for repeat users. Prices and willingness to pay remain unvalidated. |
| Main variable costs | OCR, model input/output, repeated assessment, private storage and professional checklist maintenance. |
| First validation measures | Correctly detected gaps, false missing-evidence warnings, correction time, reviewer follow-up requests, and measured cost per completed case. |

No billing integration is required for the hackathon. Do not present a proposed business model as proven demand.

### End-to-end user journey

1. **Describe:** enter the supported case type, parties, dates, amount, requested outcome and short narrative.
2. **Clarify:** answer targeted intake questions when the description lacks necessary information.
3. **Upload:** add documents; see which files were accepted and which pages can be read.
4. **Assess:** explicitly start analysis of the current case revision.
5. **Understand:** inspect validated findings and their source passages, including uncertainty and incomplete coverage.
6. **Fix:** provide acceptable evidence or record a correction, explanation or disagreement.
7. **Reassess:** see which stable findings remain open, are resolved, reopen or cease to apply.
8. **Share:** review and explicitly submit an immutable dossier version to an assigned platform reviewer, retaining unresolved issues and limitations.
9. **Review:** the recipient opens that version and can request clarification; the preparer can later submit a new version.

Preparation delivers value without a government integration. Back-office receipt is an application workflow, not an official court filing. A demonstration can use a seeded mediator or arbitrator reviewer account; it must not imply official institutional access or authority.

### What â€œexistenceâ€ and â€œintegrityâ€ mean

| Check family | Included behavior | Limit of the conclusion |
| --- | --- | --- |
| File presence | Track uploaded documents and references to expected attachments. | Absence from the uploaded set is not proof that a document does not exist elsewhere. |
| Evidence completeness | Assess fixed checklist items using acceptable alternative evidence and relevant transaction links. | Completing the checklist does not prove that every legally necessary item has been identified. |
| Readability | Detect parsing failures, unreadable pages and insufficient source coverage. | OCR output can itself contain errors. |
| Internal consistency | Flag supported mismatches in parties, document references, dates or recorded amounts within the supported rules. | A mismatch is a question to resolve, not an accusation of fraud. |
| Original preservation | Keep original bytes, hashes, document versions and submitted manifests. | A hash detects later byte changes; it does not authenticate the uploaded original. |
| Source traceability | Validate quotes against stored page text before publishing dependent findings. | A matching quote does not guarantee that the model interpreted it correctly. |

Excluded: expert technical investigation, document or signature authentication, legal admissibility certification, liability decisions, compensation valuation, win probabilities, automatic legal notices, automated filing, mediation negotiation and government integration.

### Confirmed boundaries and proposed defaults

The confirmed constraints are one preparer experience, a limited reviewer back office, the correction/reassessment loop, source validation before display, fixed reviewed legal/checklist selection, and deterministic monetary arithmetic.

The narrow initial category `unpaid_goods_invoice`, TND-only monetary handling, French interface with Arabic source support, React/TypeScript frontend, Python/FastAPI backend and PostgreSQL are **proposed implementation defaults**. The model provider and actual model ID must be chosen against available credits and tested capabilities. These are not silently approved decisions.

For the demo, prefer a small accurate evidence checklist over broad Tunisian-law retrieval. A practitioner must review any checklist presented as a legal requirement. Until then, label the pack unvalidated and demonstrate evidence guidance and document checks without claiming legal coverage.

### AI and automation division

| Responsibility | Owner |
| --- | --- |
| Reject unsupported intake; determine follow-up fields | Backend rules; optional bounded semantic intake call |
| Store files, create page registry and obtain source text | Backend/OCR worker |
| Extract literal facts and locate relevant evidence | Constrained model calls |
| Validate references, quotes, schemas and permitted outputs | Backend |
| Select checklist and fixed legal references | Backend using reviewed versioned assets |
| Judge supplied checks against evidence | Model, subject to validation and abstention |
| Parse amounts, deduplicate linked records and calculate balances | Decimal application code |
| Maintain finding identity, revisions, permissions and packages | Backend |
| Decide whether to correct, disagree or submit | Preparer |
| Conduct professional review and any expert investigation | Human reviewer or expert |

The runtime is a small application with an API and a background worker, not an autonomous agent system. Reuse validated extraction for unchanged files and keep a hard spending ceiling. Fixture mode supports development and fallback rehearsal but must always be visibly identified; it must never masquerade as a successful live analysis.

### Hackathon delivery target

Deliver one complete correction loop for one supported category: an initial evidence gap, a source-backed correction, a validated reassessment and a reviewer snapshot. A narrowly linked invoice/payment discrepancy can demonstrate deterministic arithmetic without expanding into expert valuation.

Use synthetic documents. Measure actual latency and model cost on the implemented demo. Keep real-client onboarding, provider data handling, retention policy, production hosting and jurisdiction-specific professional review as explicit pilot decisions rather than pretending the hackathon prototype is already production-ready.

International expansion is a later hypothesis: add a separately reviewed jurisdiction/checklist pack, formats and language support, while preserving the same provenance and revision pipeline. It is not accomplished by translating the UI or asking the model to choose foreign law. An Opalexe-like ecosystem is outside this MVP.



---

# Frontend specification

Owner: **UI â€” Contributor 1**. Coordinates with API through B9.

## F1. Product and scope

Build the interface for a Tunisian contract-dispute document-preparation SaaS. A business owner or lawyer uses one role, `preparer`, to describe a dispute, upload documents, identify evidence gaps, respond and reassess. A separate `reviewer` receives a submitted dossier version.

The AI checks expected item existence, readability and consistency against a controlled checklist. It does not replace an expert's technical investigation, decide liability, estimate compensation, authenticate signatures or certify evidence as genuine. Monetary reconciliation and legal-reference attachment belong to backend code.

The product must distinguish:

- An expected file or referenced annex was not found in the material reviewed.
- A file exists but cannot be read or its content is inconsistent.
- A checklist item appears supported by cited information.
- An item cannot be assessed and needs clarification or professional review.

â€œIntegrityâ€ means these bounded checks and preservation of the uploaded original. Never show â€œauthentic,â€ â€œlegally valid,â€ â€œexpert-approved,â€ â€œcourt-approvedâ€ or a probability of winning based on AI output.

The government is not involved in preparation. Back-office receipt is receipt in this application, not official judicial filing.

## F2. Two-person ownership

UI owns React/TypeScript views, navigation, accessibility, API client, frontend fixtures, source previews and browser verification. API owns schemas, all permissions, legal check selection, AI calls, validation, calculations, persistence, exports and submission snapshots.

The **B9 contract below is authoritative** for request fields, statuses, response shapes, errors and routes. UI may use mock data matching that contract while API builds. No production legal rules, money calculation or model-provider SDK belongs in the frontend.

Use a single `CaseApi` adapter boundary. Future fixture and HTTP implementations must expose the same methods. Fixture mode is visibly labelled â€œDemo data â€” no live analysis.â€ Never present a seeded response as a live AI result.

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

Names are 1â€“200 characters after trimming. Narrative is 30â€“4,000 characters; the backend also checks whether the description is meaningful. Amount is entered as a decimal string, never converted through JavaScript floating-point arithmetic. French comma input may be converted to a canonical dot only when unambiguous; otherwise ask for clarification.

The intake gate can return targeted questions, for example â€œWhat goods were supplied?â€ or â€œWhich payment remains disputed?â€ Show each question next to its mapped input or as a short answer field. Persist answers through the claim-revision endpoint. Do not show an under-specified claim as â€œAI analysis failed.â€

If intake requires more information, keep the draft and uploaded files. The expensive assessment cannot start until the gate is ready.

### Document workspace

Show filename, server document type, pages, upload time, reading state and errors. Upload progress is separate from analysis progress. Preview originals through authorized endpoints, with Arabic text in `dir="auto"` containers. Escape all document text; do not render uploaded HTML.

Required states: uploaded, processing, ready, partial, unreadable and rejected. Do not imply that `ready` means authentic. A duplicate is identified by the server; show the existing document instead of silently adding a second copy.

The preparer can remove an active document or upload a replacement. Removal increments the working revision and leaves previously submitted snapshots unchanged. No automatic analysis on each file selection: use the explicit action button.

Upload selected files sequentially using the latest server-returned revision, because each successful upload changes the case. Do not dispatch multiple revision-checked uploads in parallel and hide their conflicts. A duplicate does not increment the revision.

### Analysis and findings

Only render backend-published analysis responses. Never render streamed model text, unvalidated extraction or intermediate model reasoning.

Job states: `queued`, `running`, `succeeded`, `failed`, `superseded`. Running phases: `reading`, `extracting`, `validating_facts`, `checking`, `validating_checks`, `publishing`.

Poll every 2 seconds initially, then every 5 seconds after 30 seconds. Stop on terminal states or when leaving the view. A transport error stops neither the server job nor its stored progress. Reopening the case restores the active job. After a UI wait threshold, display â€œStill processingâ€ with retry-status controls; do not claim server failure from a browser timeout.

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

Use neutral copy such as â€œEvidence not found in the reviewed materialâ€ and â€œThe amount differs from the documented records.â€ Do not imply fraud or concealment.

If normalized text offsets are unavailable, open the cited page and show the matched quote beside it. Do not invent a bounding box or place an approximate highlight as if exact.

### Respond and reassess

Actions: `add_evidence`, `correct_claim`, `explain_unavailable`, `disagree`.

A response does not make a finding resolved. The next validated assessment determines its current state. User disagreement remains visible in the case history and submission. For an upload response, attach document IDs already owned by the case.

The backend supplies the change set: `new`, `resolved`, `still_open`, `reopened`, `not_applicable`. The frontend must not match findings by generated title or array position.

### Final review and submission

Display the latest revision, validated analysis coverage, claim summary, evidence index, unresolved findings and preparer explanations. `ready_for_review` is a workflow state, not a legal certificate.

Require explicit confirmation of the dossier version and chosen available recipient. Submit with `expected_revision` and an idempotency key. If the server reports a changed revision, reload and ask the user to review again.

An explicitly acknowledged partial assessment can be submitted with disclosures if the backend allows it. A failed or unvalidated run cannot be presented as an assessed dossier. Missing documents are not an endless compulsory-upload gate.

The downloadable package is produced by the backend. Show actual states: generating, ready, failed. After submission, display submission ID, version, recipient and timestamp. Use â€œTransmis pour examen sur la plateforme,â€ not â€œDÃ©posÃ© au tribunal.â€

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
  "message": "Aucune preuve de rÃ©ception trouvÃ©e dans les piÃ¨ces examinÃ©es.",
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


---

# Backend and AI specification

Owner: **API â€” Contributor 2**. Section B9 defines the shared integration contract.

## B1. Scope and hard boundaries

Prepare contract-dispute documents before professional review. Check expected item/file existence, readability, references, internal consistency and preservation of originals. Do not replace expert investigation, decide liability or damages, authenticate evidence or certify legal validity.

â€œIntegrityâ€ is bounded: original bytes are preserved, later byte changes are detectable, cited text is located in stored page text and defined consistency checks run. None proves the original is genuine. A hash is not an authenticity certificate; OCR is not independent confirmation of a scan's truth.

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

Provider selection remains pending the team's credits. Choose one accessible model that supports the required constrained output schema, then test it on the synthetic French/Arabic case set. Configure the provider/model externally and implement only the selected live provider for the hackathon, plus explicit fixture mode. This documentation does not assert model access, current pricing or successful testing.

## B3. Structured intake and cheap gate

### Input constraints

| Field | Rule |
| --- | --- |
| `case_type` | Exact enum; reject unsupported values before any model call |
| `claimant_name`, `counterparty_name` | Trimmed, 1â€“200 characters each |
| `claimed_amount` | Nonnegative canonical decimal string, maximum 12 integer digits and 3 fractional digits for TND; never a JSON float |
| `currency` | `TND` for this MVP |
| `dates` | Explicit keys `contract`, `delivery`, `invoice`, `payment_due`, each ISO date or null |
| `requested_outcome` | Exact enum |
| `narrative` | Trimmed, 30â€“4,000 characters; never treated as trusted instructions |
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

Each legal reference includes ID, code/article, original text, language, source URL/page, applicable dates where established, conditions, exceptions/related references, review status, reviewer and review date. Unknown effective dates must remain unknown. No invented articles or â€œlawyer-reviewedâ€ labels.

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

Compute `documented_balance = invoice_total - linked_payments - linked_credit_notes` only when all inputs and links are unambiguous. Do not assume an absent receipt proves zero payments: label the result â€œbalance based on uploaded records.â€ If links or signs are uncertain, publish an unresolved reconciliation check. The claimed amount comes from structured user input, not model output.

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
    {"id": "describe_goods", "field": "narrative", "message": "Quels biens ont Ã©tÃ© fournis ?"}
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
      "message": "Aucune preuve de rÃ©ception trouvÃ©e dans les piÃ¨ces examinÃ©es.",
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

- [S1: Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/) â€” validate output/input types; strict mode still requires explicit domain validation.
- [S2: FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/) â€” separate container startup and application lifecycle concerns.
- [S3: Docker Compose readiness](https://docs.docker.com/compose/how-tos/startup-order/) â€” a running database container is not necessarily ready; configure health checks.
- [S4: Tesseract language data](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html) â€” install the language data used by the scan path.

These are implementation references, not evidence that this prototype is already built or validated. No legal article was authored or certified as part of this spec split.


---

# Local development specification

**Planned environment only.** No application, Dockerfiles, Compose services, migrations or seed commands have been implemented or run. Commands below become usable after those assets exist. API owns infrastructure; UI owns its startup and proxy configuration.

## L1. Recommended environment

Use Docker Compose for a reproducible integrated demo. Use browser fixtures while frontend work is independent. Do not pay for model calls to develop screen layouts.

Proposed runtime baselines: Node.js 22, Python 3.11 and PostgreSQL 16. These are compatibility choices, not a claim to be the latest versions. Pin tested package versions and commit lockfiles when development is authorized.

| Future service | Role | Local access |
| --- | --- | --- |
| `web` | React/Vite development server | `http://localhost:5173` |
| `api` | FastAPI, sessions, uploads and read endpoints | `http://localhost:8000`; browser normally uses web proxy |
| `worker` | Jobs, extraction/OCR, AI, validation and export | No public port |
| `db` | PostgreSQL state and job queue | Internal `db:5432`; do not expose by default |

One API process and one worker are enough. Use a persistent DB volume and a private file volume mounted by API and worker. The web container must not receive file storage or provider credentials.

Browser calls relative `/api/...`; Vite proxies to `api:8000` in Compose or `127.0.0.1:8000` when Vite runs on the host. This preserves a single browser origin for cookies and CSRF behavior. FastAPI includes the `/api` prefix; the proxy must not remove it.

Development sessions use HttpOnly cookies, explicit SameSite policy and CSRF tokens on mutations. `Secure=false` is a local HTTP exception only; use HTTPS and secure cookies in deployed environments. Fixture authentication is isolated and visibly marked.

## L2. Future repository layout

Only `spec/` documents currently belong to this deliverable. Create the following implementation assets later:

| Path | Owner | Future purpose |
| --- | --- | --- |
| `frontend/` | UI | React/TypeScript app, `npm run dev`, lockfile |
| `frontend/src/api/` | UI | Fixture/HTTP adapters matching B9 |
| `backend/app/main.py` | API | FastAPI entry point |
| `backend/app/worker.py` | API | Worker entry point |
| `backend/app/seed_demo.py` | API | Idempotent synthetic data/account seeding |
| `backend/app/legal_packs/` | API | Versioned checklist/reference files and review labels |
| `backend/migrations/` | API | Alembic schema migrations |
| `backend/tests/` | API | Deterministic, validation and access-boundary checks |
| `fixtures/` | API, with UI agreement | Synthetic source documents and expected outcomes |
| `compose.yaml` | API | `web`, `api`, `worker`, `db` |
| `.env.example` | API | Nonsecret environment documentation |
| `.env` | Each contributor locally | Private credentials; git-ignored |

Do not create an unrelated `shared` service or a second backend just for AI.

## L3. Environment contract

This table describes the future `.env.example`; it is not a request to share secrets.

| Variable | Default or expected value | Consumer |
| --- | --- | --- |
| `APP_ENV` | `development` | API/worker |
| `DATABASE_URL` | PostgreSQL URL using host `db` in Compose; driver matches installed SQLAlchemy driver | API/worker |
| `POSTGRES_DB` | `dispute_demo` | Database |
| `POSTGRES_USER` | `dispute_demo` | Database |
| `POSTGRES_PASSWORD` | Developer-generated local secret | Database/API/worker |
| `SESSION_SECRET` | Developer-generated random secret, never a committed value | API |
| `COOKIE_SECURE` | `false` locally; `true` with HTTPS | API |
| `APP_ORIGIN` | `http://localhost:5173` | API |
| `FILE_STORAGE_ROOT` | `/data/private` in containers | API/worker |
| `AI_MODE` | `fixture` by default; `live` only when enabled deliberately | API/worker |
| `AI_PROVIDER` | Selected provider; not yet confirmed | Worker/intake adapter |
| `AI_MODEL` | Accessible tested model ID; not yet confirmed | Worker/intake adapter |
| `AI_API_KEY` | Provider credential, never frontend-visible | Worker/intake adapter |
| `AI_ENDPOINT` | Optional provider endpoint, required if the chosen provider needs it | Worker/intake adapter |
| `AI_DEMO_BUDGET_USD` | `0` in fixture mode; explicit cap needed for live mode | API/worker |
| `AI_MAX_CONCURRENCY` | `1` | Worker |
| `LEGAL_PACK_VERSION` | `tn-goods-v1` initial asset version | API/worker |
| `MAX_CASE_FILES` | `10` | API/worker |
| `MAX_CASE_PAGES` | `30` | API/worker |
| `MAX_FILE_BYTES` | `10485760` | API |
| `MAX_CASE_BYTES` | `52428800` | API |
| `OCR_LANGUAGES` | `fra+ara+eng` | Worker |
| `API_PROXY_TARGET` | `http://api:8000` in Compose | Vite server, not browser secret |
| `VITE_DATA_MODE` | `fixture` or `http` | Frontend |

Fixture mode must avoid provider calls entirely, including health checks and intake. Live mode must fail configuration validation if credentials, model or spending ceiling are absent. Do not silently switch to fixture results after a live provider failure.

## L4. Planned Docker startup

Prerequisite: both contributors have subsequently implemented the layout, Dockerfiles, Compose services, migration setup, seed script and commands named here.

Each contributor creates their private `.env` from the future `.env.example` and supplies local values. Do not include real case data or API keys in screenshots, fixtures or source control.

Run from the future repository root:

```bash
docker compose build
docker compose up -d --wait db
docker compose run --rm api alembic upgrade head
docker compose run --rm api python -m app.seed_demo
docker compose up -d api worker web
docker compose ps
```

The backend image's working directory and installed application package must make the Alembic and `python -m app...` commands valid. `api` should start through `uvicorn app.main:app --host 0.0.0.0 --port 8000`; `worker` through `python -m app.worker`. Vite must listen on `0.0.0.0:5173` inside its container.

Compose must use a database health check and healthy dependency condition. A running container is not enough to prove PostgreSQL is accepting requests; Docker documents this distinction in its [startup-order guide](https://docs.docker.com/compose/how-tos/startup-order/).

Do not run migrations independently in every API/worker process. Run the single migration step before starting them, as above. Mount the same private files volume into API and worker. Install the PDF renderer and Tesseract language files in the worker image.

## L5. Independent work before integration

### UI work

After the frontend package exists, set its local `VITE_DATA_MODE=fixture` and run in `frontend/`:

```bash
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

`npm ci` requires a committed lockfile; creating that initial package/lockfile is a later development task. Match all fixtures to B9. No backend or live AI is required in browser fixture mode.

### API work

Use Docker `db`, `api` and `worker` in backend fixture mode, then test API operations through `http://localhost:8000/docs`. Seed two preparers and one reviewer. Validated fixture output should pass through the real validators, persistence and submission logic rather than bypass them.

Mock authentication shortcuts must not replace the integrated server authorization. Keep intentionally invalid model-output fixtures for backend validation tests; never publish them directly as demo UI data.

### Integrated mode without spending credits

Set `VITE_DATA_MODE=http` and `AI_MODE=fixture`. Restart API/worker and restart Vite if its environment changed. This exercises real sessions, documents, jobs, validators, reassessment and reviewer handoff using clearly labelled deterministic AI fixtures.

### Live demonstration

After provider access and fixture acceptance checks pass, set `AI_MODE=live`, the actual provider/model/endpoint, private credential and a small positive spending ceiling. Restart the relevant services. Run a single known synthetic case and inspect measured usage before rehearsing additional cases.

Run only one live worker for the demo. Do not rely on assumed provider support or latency; log the first successful result in progress.md.

## L6. Planned verification and troubleshooting

```bash
curl http://localhost:8000/api/health/live
curl http://localhost:8000/api/health/ready
docker compose logs --tail=100 api worker
```

These checks become useful after implementation. Logs must redact secrets and document content.

| Symptom | Check |
| --- | --- |
| Browser cannot reach API | Vite proxy target differs for host versus container execution |
| Login does not persist | Proxy, cookie host/flags and request credentials; no mixed `localhost`/`127.0.0.1` session origins |
| Mutation rejected | Valid CSRF token and current revision |
| Jobs remain queued | Worker running, DB lease and permissions; no provider calls needed to diagnose a queued job |
| Scan facts all rejected | OCR language installation, stored page text and quote matching; do not weaken validation to make demo green |
| A corrected upload changes nothing | Reassessment revision, active document registry and cache version |
| Provider limit reached | Show retryable error; preserve case; do not silently generate fixture answers |
| Reviewer sees no case | Submission is explicit and recipient assignment must match signed-in reviewer |

Stop the future environment with `docker compose stop`; containers and named data volumes remain. Do not use `docker compose down -v` unless intentionally deleting disposable demo data. No such command has been run for this task.

API owns final verification that these commands match the implemented entry points; UI verifies that the browser can complete the entire loop from a fresh startup.


---

# Two-person delivery and progress baseline

Planning snapshot: **UI â€” Contributor 1** owns the frontend; **API â€” Contributor 2** owns the backend and AI. Replace these labels with your names. Maintain ongoing task status in [progress.md](progress.md).

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
| UI-09 | HTTP adapter integration and FE-01â€“FE-12 checks | Not started | API contract implemented | |

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
| API-10 | Exports and immutable reviewer submission | Not started | API-07â€“API-09 | |
| API-11 | Compose, seed accounts and actual startup guide verification | Not started | API-02 | |
| API-12 | BE-01â€“BE-15 and live credit-limited smoke check | Not started | API-03â€“API-11 | |

API is the heavier track. Keep one provider/category and finish the validated response contract early so UI can integrate. Optional intake semantic AI can be deferred; source verification and deterministic calculations cannot.

## P5. Joint handoff schedule

Times are a proposed allocation within the 24-hour hackathon, not actual progress timestamps.

| Time | UI handoff | API handoff | Integration result |
| --- | --- | --- | --- |
| Hours 0â€“2 | Agree screens and fixture responses | Agree B9, provider, checklist and synthetic case | Contract freeze v1 |
| Hours 2â€“7 | Intake/documents against fixtures | Sessions, intake and document registry | First real case and upload |
| Hours 7â€“13 | Findings/source viewer and response loop | Validated checks and deterministic money output | One analysed case in UI |
| Hours 13â€“18 | Reassessment and reviewer screens | Versioned findings, export/submission | Correction loop and handoff |
| Hours 18â€“22 | Integrated browser acceptance checks | Boundary tests, live model/usage check | Known limitations recorded |
| Hours 22â€“24 | Demo rehearsal | Startup/recovery and quota check | Three-minute end-to-end proof |

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