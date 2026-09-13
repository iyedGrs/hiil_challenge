import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../ApiError";
import { FIXTURE_DEMO_PASSWORD, FIXTURE_USERS } from "./seed";
import { FixtureCaseApi } from "./FixtureCaseApi";

describe("FixtureCaseApi", () => {
  let api: FixtureCaseApi;

  beforeEach(() => {
    api = new FixtureCaseApi();
  });

  it("returns config without requiring auth", async () => {
    const config = await api.getConfig();
    expect(config.case_types).toContain("unpaid_goods_invoice");
    expect(config.execution_mode).toBe("fixture");
  });

  it("rejects getCurrentUser before login", async () => {
    await expect(api.getCurrentUser()).resolves.toBeNull();
  });

  it("logs a seeded account in and restores it via getCurrentUser", async () => {
    const preparer = FIXTURE_USERS.find((u) => u.role === "preparer")!;
    const session = await api.login(preparer.email, FIXTURE_DEMO_PASSWORD);
    expect(session.user.email).toBe(preparer.email);
    expect(session.csrf_token).toBeTruthy();

    const restored = await api.getCurrentUser();
    expect(restored?.user.email).toBe(preparer.email);
  });

  it("rejects an invalid password", async () => {
    const preparer = FIXTURE_USERS[0];
    await expect(api.login(preparer.email, "wrong-password")).rejects.toBeInstanceOf(ApiError);
  });

  it("logout clears the session so getCurrentUser returns null again", async () => {
    const preparer = FIXTURE_USERS[0];
    await api.login(preparer.email, FIXTURE_DEMO_PASSWORD);
    await api.logout();
    await expect(api.getCurrentUser()).resolves.toBeNull();
    // Every case-scoped call must now fail closed rather than leaking prior-user data.
    await expect(api.listCases()).rejects.toMatchObject({ status: 401 });
  });

  it("seeds the demo case (P6: 20,000 TND unpaid_goods_invoice) for its owning preparer", async () => {
    await api.login("amina.preparer@example.tn", FIXTURE_DEMO_PASSWORD);
    const { items } = await api.listCases();
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      case_type: "unpaid_goods_invoice",
      claimed_amount: "20000.000",
      currency: "TND",
    });
  });

  const BASE_CLAIM = {
    case_type: "unpaid_goods_invoice",
    claimant_name: "Demo Supplier",
    counterparty_name: "Demo Customer",
    claimed_amount: "20000.000",
    currency: "TND",
    dates: { contract: null, delivery: null, invoice: null, payment_due: null },
    requested_outcome: "payment",
    follow_up_answers: [],
  };

  describe("intake gate", () => {
    beforeEach(async () => {
      await api.login("amina.preparer@example.tn", FIXTURE_DEMO_PASSWORD);
    });

    it("rejects an unsupported case type with 422 UNSUPPORTED_CASE_TYPE before creating a case", async () => {
      await expect(
        api.createCase({
          ...BASE_CLAIM,
          case_type: "personal_injury",
          narrative: "Une description suffisamment longue pour dépasser le seuil minimal de trente caractères.",
        }),
      ).rejects.toMatchObject({ status: 422, code: "UNSUPPORTED_CASE_TYPE" });
    });

    it("asks what goods were supplied when the narrative never mentions them", async () => {
      const { intake } = await api.createCase({
        ...BASE_CLAIM,
        narrative: "Le client n'a pas payé la facture correspondant à la commande passée en juin.",
      });
      expect(intake.status).toBe("needs_information");
      expect(intake.questions).toEqual([
        { id: "describe_goods", field: "narrative", message: "Quels biens ont été fournis ?" },
      ]);
    });

    it("becomes ready once the narrative is edited to mention the goods", async () => {
      const created = await api.createCase({
        ...BASE_CLAIM,
        narrative: "Le client n'a pas payé la facture correspondant à la commande passée en juin.",
      });
      expect(created.intake.status).toBe("needs_information");

      const updated = await api.updateClaim(created.case_id, created.revision, {
        ...BASE_CLAIM,
        narrative: "Nous avons fourni des biens (mobilier de bureau) et la facture reste impayée.",
      });
      expect(updated.intake.status).toBe("ready");
      expect(updated.revision).toBe(created.revision + 1);
    });

    it("becomes ready once the mapped follow-up question is answered instead", async () => {
      const created = await api.createCase({
        ...BASE_CLAIM,
        narrative: "Le client n'a pas payé la facture correspondant à la commande passée en juin.",
      });

      const updated = await api.updateClaim(created.case_id, created.revision, {
        ...BASE_CLAIM,
        narrative: "Le client n'a pas payé la facture correspondant à la commande passée en juin.",
        follow_up_answers: [{ question_id: "describe_goods", answer: "Du mobilier de bureau." }],
      });
      expect(updated.intake.status).toBe("ready");
    });

    it("reuses the cached gate result for an unchanged claim revision", async () => {
      const created = await api.createCase({
        ...BASE_CLAIM,
        narrative: "Le client n'a pas payé la facture correspondant à la commande passée en juin.",
      });
      const checked = await api.checkIntake(created.case_id, created.revision);
      expect(checked).toEqual(created.intake);
    });
  });

  describe("documents (UI-04)", () => {
    const CASE_ID = "CASE_001"; // seeded demo case, revision 1, 5 documents

    beforeEach(async () => {
      await api.login("amina.preparer@example.tn", FIXTURE_DEMO_PASSWORD);
    });

    function pdf(name: string, size = 1024): File {
      return new File([new Uint8Array(size)], name, { type: "application/pdf" });
    }

    it("uploads a document and chains the returned revision", async () => {
      const first = await api.uploadDocument(CASE_ID, 1, pdf("piece_1.pdf"));
      expect(first.duplicate).toBe(false);
      expect(first.revision).toBe(2);

      const second = await api.uploadDocument(CASE_ID, first.revision, pdf("piece_2.pdf"));
      expect(second.duplicate).toBe(false);
      expect(second.revision).toBe(3);
    });

    it("rejects an upload against a stale revision with REVISION_CONFLICT", async () => {
      await api.uploadDocument(CASE_ID, 1, pdf("piece_1.pdf"));
      await expect(api.uploadDocument(CASE_ID, 1, pdf("piece_2.pdf"))).rejects.toMatchObject({
        status: 409,
        code: "REVISION_CONFLICT",
      });
    });

    it("returns duplicate:true without bumping the revision for a same name/size upload", async () => {
      const first = await api.uploadDocument(CASE_ID, 1, pdf("piece_1.pdf", 2048));
      const dup = await api.uploadDocument(CASE_ID, first.revision, pdf("piece_1.pdf", 2048));
      expect(dup.duplicate).toBe(true);
      expect(dup.revision).toBe(first.revision);
      expect(dup.document.document_id).toBe(first.document.document_id);
    });

    it("rejects an unsupported MIME type with 415 UNSUPPORTED_FILE", async () => {
      const file = new File(["x"], "malware.exe", { type: "application/x-msdownload" });
      await expect(api.uploadDocument(CASE_ID, 1, file)).rejects.toMatchObject({
        status: 415,
        code: "UNSUPPORTED_FILE",
      });
    });

    it("rejects a file over the per-file byte limit with 413 FILE_LIMIT", async () => {
      const config = await api.getConfig();
      const oversized = pdf("gros_fichier.pdf", config.limits.max_file_bytes + 1);
      await expect(api.uploadDocument(CASE_ID, 1, oversized)).rejects.toMatchObject({
        status: 413,
        code: "FILE_LIMIT",
      });
    });

    it("rejects a new file once the active-file count limit is reached", async () => {
      const config = await api.getConfig();
      let revision = 1;
      // 5 seeded documents already active; fill up to the limit.
      for (let i = 0; i < config.limits.max_active_files - 5; i += 1) {
        const result = await api.uploadDocument(CASE_ID, revision, pdf(`extra_${i}.pdf`));
        revision = result.revision;
      }
      await expect(api.uploadDocument(CASE_ID, revision, pdf("one_too_many.pdf"))).rejects.toMatchObject({
        status: 413,
        code: "FILE_LIMIT",
      });
    });

    it("deletes a document and chains the revision", async () => {
      const result = await api.deleteDocument(CASE_ID, "DOC_001", 1);
      expect(result.revision).toBe(2);
      const detail = await api.getCase(CASE_ID);
      expect(detail.documents.find((d) => d.document_id === "DOC_001")?.active).toBe(false);
    });

    it("returns a page preview with source text in the right method/quality shape", async () => {
      const page = await api.getDocumentPage("DOC_001", 1);
      expect(page.source_text).toBeTruthy();
      expect(page.method).toBe("embedded_text");
    });

    it("returns the seeded Arabic page text unchanged", async () => {
      const page = await api.getDocumentPage("DOC_005", 1);
      expect(page.source_text).toContain("نطالب");
    });
  });

  describe("analysis jobs (UI-06)", () => {
    const CASE_ID = "CASE_001"; // seeded demo case, revision 1, 1 published analysis

    beforeEach(async () => {
      vi.useFakeTimers();
      await api.login("amina.preparer@example.tn", FIXTURE_DEMO_PASSWORD);
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it("advances a started job through the running phases before succeeding", async () => {
      const started = await api.startAnalysis(CASE_ID, 1, "idem-phases");
      expect((await api.getJob(started.job_id)).status).toBe("queued");

      await vi.advanceTimersByTimeAsync(400);
      let job = await api.getJob(started.job_id);
      expect(job.status).toBe("running");
      expect(job.phase).toBe("reading");

      await vi.advanceTimersByTimeAsync(400 * 6);
      job = await api.getJob(started.job_id);
      expect(job.status).toBe("succeeded");
      expect(job.result_analysis_id).toBeTruthy();
    });

    it("resolves the missing-delivery-evidence finding once evidence is added, keeps others still_open, and introduces one new finding on the second run (P6)", async () => {
      const responded = await api.respondToFinding("finding_delivery_invoice_0001", 1, "add_evidence", null, ["DOC_001"]);

      const started = await api.startAnalysis(CASE_ID, responded.revision, "idem-reassess");
      await vi.advanceTimersByTimeAsync(400 * 7);
      const job = await api.getJob(started.job_id);
      const analysis = await api.getAnalysis(job.result_analysis_id!);

      const delivery = analysis.checks.find((c) => c.finding_id === "finding_delivery_invoice_0001")!;
      expect(delivery.finding_status).toBe("resolved");
      expect(delivery.delta).toBe("resolved");

      const amount = analysis.checks.find((c) => c.finding_id === "finding_amount_reconciliation_0001")!;
      expect(amount.finding_status).toBe("open");
      expect(amount.delta).toBe("still_open");

      const newFinding = analysis.checks.find((c) => c.finding_id === "finding_payment_due_status_0001");
      expect(newFinding?.delta).toBe("new");
    });

    it("marks a still-active job superseded when a new analysis is started for the same case", async () => {
      const first = await api.startAnalysis(CASE_ID, 1, "idem-first");
      await vi.advanceTimersByTimeAsync(400); // first job now running, not yet succeeded

      const second = await api.startAnalysis(CASE_ID, 1, "idem-second");
      expect(second.job_id).not.toBe(first.job_id);
      expect((await api.getJob(first.job_id)).status).toBe("superseded");
    });

    it("returns the same job for a retried idempotency key instead of starting a duplicate", async () => {
      const first = await api.startAnalysis(CASE_ID, 1, "idem-retry");
      const retried = await api.startAnalysis(CASE_ID, 1, "idem-retry");
      expect(retried.job_id).toBe(first.job_id);
    });
  });

  describe("reviewer back office (UI-08)", () => {
    const CASE_ID = "CASE_001"; // seeded demo case, revision 1, published analysis RUN_001

    /**
     * The seeded demo analysis is deliberately unresolved (some checks
     * `unassessable`/`contradicted`), so submission is refused by the
     * automatic readiness gate (spec/progress.md change log). Force it into
     * the shape a genuinely complete, live run would have — the same
     * approach backend/tests/test_handoff.py's `force_complete_verdict`
     * takes — so these tests can exercise the reviewer read paths.
     */
    function forceCompleteVerdict(): void {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any -- reach into the private fixture store, test-only
      const record = (api as any).store.cases.get(CASE_ID);
      const analysis = record.analyses.find((a: { analysis_id: string }) => a.analysis_id === "RUN_001");
      analysis.execution_mode = "live";
      analysis.status = "ready";
      analysis.coverage = { ...analysis.coverage, unreadable_pages: 0 };
      for (const check of analysis.checks) {
        check.result = "satisfied";
        check.finding_status = null;
      }
    }

    async function submitDemoCase(): Promise<string> {
      await api.login("amina.preparer@example.tn", FIXTURE_DEMO_PASSWORD);
      forceCompleteVerdict();
      const submission = await api.createSubmission(
        CASE_ID,
        1,
        "RUN_001",
        "recipient_reviewer_demo",
        false,
        "idem-submit",
      );
      return submission.submission_id;
    }

    it("refuses submission while the automatic verdict is not complete", async () => {
      await api.login("amina.preparer@example.tn", FIXTURE_DEMO_PASSWORD);
      await expect(
        api.createSubmission(CASE_ID, 1, "RUN_001", "recipient_reviewer_demo", false, "idem-blocked"),
      ).rejects.toMatchObject({ status: 409 });
    });

    it("lets the assigned reviewer see and act on a submission", async () => {
      const submissionId = await submitDemoCase();
      await api.login("reviewer@example.tn", FIXTURE_DEMO_PASSWORD);

      const { items } = await api.listReviewerSubmissions();
      expect(items.map((s) => s.submission_id)).toContain(submissionId);

      const detail = await api.getReviewerSubmission(submissionId);
      expect(detail.claim.claimant_name).toBe("Amina Gharbi");
    });

    it("keeps the preparer's role from calling reviewer-only routes", async () => {
      const submissionId = await submitDemoCase();
      // still logged in as the preparer
      await expect(api.listReviewerSubmissions()).rejects.toMatchObject({ status: 404 });
      await expect(api.getReviewerSubmission(submissionId)).rejects.toMatchObject({ status: 404 });
      await expect(api.createReviewEvent(submissionId, "received", null)).rejects.toMatchObject({ status: 404 });
    });

    it("returns not-found for an unknown submission id, honestly rather than leaking existence", async () => {
      await api.login("reviewer@example.tn", FIXTURE_DEMO_PASSWORD);
      await expect(api.getReviewerSubmission("SUB_DOES_NOT_EXIST")).rejects.toMatchObject({ status: 404 });
    });

    it("FE-09: a reviewer keeps seeing the submitted revision after the preparer edits the working case", async () => {
      const submissionId = await submitDemoCase();
      // Preparer edits the claim and uploads a new document after submitting.
      await api.updateClaim(CASE_ID, 1, {
        case_type: "unpaid_goods_invoice",
        claimant_name: "Amina Gharbi (modifié)",
        counterparty_name: "Client Démo SARL",
        claimed_amount: "99999.000",
        currency: "TND",
        dates: { contract: null, delivery: null, invoice: null, payment_due: null },
        requested_outcome: "payment",
        narrative: "Narration modifiée après la transmission du dossier pour vérifier l'immuabilité (FE-09).",
        follow_up_answers: [],
      });
      await api.uploadDocument(CASE_ID, 2, new File([new Uint8Array(10)], "nouvelle_piece.pdf", { type: "application/pdf" }));

      await api.login("reviewer@example.tn", FIXTURE_DEMO_PASSWORD);
      const detail = await api.getReviewerSubmission(submissionId);

      expect(detail.claim.claimant_name).toBe("Amina Gharbi");
      expect(detail.claim.claimed_amount).toBe("20000.000");
      expect(detail.documents.some((d) => d.filename === "nouvelle_piece.pdf")).toBe(false);

      // Page previews are read from the frozen snapshot's documents too.
      const page = await api.getDocumentPage("DOC_001", 1);
      expect(page.source_text).toContain("Facture n° 0001");
    });

    it("creates a review event and a matching activity entry in the case (clarification notification)", async () => {
      const submissionId = await submitDemoCase();
      await api.login("reviewer@example.tn", FIXTURE_DEMO_PASSWORD);

      const event = await api.createReviewEvent(submissionId, "clarification_requested", "Merci de préciser la date de livraison.");
      expect(event.message).toBe("Merci de préciser la date de livraison.");

      const detail = await api.getReviewerSubmission(submissionId);
      expect(detail.events).toHaveLength(1);

      await api.login("amina.preparer@example.tn", FIXTURE_DEMO_PASSWORD);
      const caseDetail = await api.getCase(CASE_ID);
      expect(caseDetail.activity.some((a) => a.type === "reviewer_clarification_requested")).toBe(true);
    });
  });
});
