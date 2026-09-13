import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Job } from "../api/types";
import { STILL_PROCESSING_THRESHOLD_MS, useJobPolling } from "./useJobPolling";

vi.mock("../api", () => ({
  caseApi: { getJob: vi.fn() },
}));

// eslint-disable-next-line import/order -- import after the mock so the mock is applied
import { caseApi } from "../api";

function runningJob(overrides: Partial<Job> = {}): Job {
  return { id: "JOB_001", status: "running", phase: "reading", error: null, result_analysis_id: null, result_export_id: null, ...overrides };
}

/** Flushes the pending getJob() promise (and its resulting state update) without advancing any timer. */
async function flush(): Promise<void> {
  await advance(0);
}

/** Advances fake timers inside `act` so the resulting state update is flushed before assertions. */
async function advance(ms: number): Promise<void> {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("useJobPolling", () => {
  beforeEach(() => {
    vi.mocked(caseApi.getJob).mockReset();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("polls every 2s initially, then every 5s after 30s", async () => {
    vi.mocked(caseApi.getJob).mockResolvedValue(runningJob());
    renderHook(() => useJobPolling({ jobId: "JOB_001", onSucceeded: vi.fn(), onFailed: vi.fn(), onSuperseded: vi.fn() }));

    await flush();
    expect(caseApi.getJob).toHaveBeenCalledTimes(1);

    await advance(2_000);
    expect(caseApi.getJob).toHaveBeenCalledTimes(2);
    await advance(2_000);
    expect(caseApi.getJob).toHaveBeenCalledTimes(3);

    // Calls land every 2s up to and including the 30s mark (call #1 at t=0,
    // then t=2s,4s,...,30s: 16 calls total); from there the cadence backs
    // off to 5s per spec/backend.md B9.
    await advance(26_000); // reach t=30s
    expect(caseApi.getJob).toHaveBeenCalledTimes(16);

    await advance(2_000); // short of the next 5s tick
    expect(caseApi.getJob).toHaveBeenCalledTimes(16);
    await advance(3_000); // completes the 5s interval
    expect(caseApi.getJob).toHaveBeenCalledTimes(17);
  });

  it("stops polling once the job reaches a terminal status", async () => {
    vi.mocked(caseApi.getJob).mockResolvedValue({
      id: "JOB_001",
      status: "succeeded",
      phase: "publishing",
      error: null,
      result_analysis_id: "RUN_002",
      result_export_id: null,
    });
    const onSucceeded = vi.fn();
    renderHook(() => useJobPolling({ jobId: "JOB_001", onSucceeded, onFailed: vi.fn(), onSuperseded: vi.fn() }));

    await flush();
    expect(onSucceeded).toHaveBeenCalledTimes(1);
    await advance(10_000);
    expect(caseApi.getJob).toHaveBeenCalledTimes(1);
  });

  it("stops polling on unmount and ignores any in-flight response", async () => {
    vi.mocked(caseApi.getJob).mockResolvedValue(runningJob());
    const { unmount } = renderHook(() =>
      useJobPolling({ jobId: "JOB_001", onSucceeded: vi.fn(), onFailed: vi.fn(), onSuperseded: vi.fn() }),
    );
    await flush();
    expect(caseApi.getJob).toHaveBeenCalledTimes(1);

    unmount();
    await advance(20_000);
    expect(caseApi.getJob).toHaveBeenCalledTimes(1);
  });

  it("shows a transient notice and keeps polling on a transport error, without claiming the job failed", async () => {
    vi.mocked(caseApi.getJob).mockRejectedValueOnce(new Error("network down")).mockResolvedValue(runningJob());
    const onFailed = vi.fn();
    const { result } = renderHook(() =>
      useJobPolling({ jobId: "JOB_001", onSucceeded: vi.fn(), onFailed, onSuperseded: vi.fn() }),
    );

    await flush();
    expect(result.current.transientError).toBe(true);
    expect(onFailed).not.toHaveBeenCalled();

    await advance(5_000); // network errors always back off to the 5s cadence
    expect(caseApi.getJob).toHaveBeenCalledTimes(2);
    expect(onFailed).not.toHaveBeenCalled();
  });

  it("marks stillProcessing once the wait threshold elapses, without claiming failure", async () => {
    vi.mocked(caseApi.getJob).mockResolvedValue(runningJob());
    const onFailed = vi.fn();
    const { result } = renderHook(() =>
      useJobPolling({ jobId: "JOB_001", onSucceeded: vi.fn(), onFailed, onSuperseded: vi.fn() }),
    );
    await flush();
    expect(result.current.job).not.toBeNull();
    expect(result.current.stillProcessing).toBe(false);

    await advance(STILL_PROCESSING_THRESHOLD_MS + 5_000);
    expect(result.current.stillProcessing).toBe(true);
    expect(onFailed).not.toHaveBeenCalled();
  });
});
