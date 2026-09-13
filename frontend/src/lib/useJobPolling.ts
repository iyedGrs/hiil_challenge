import { useEffect, useRef, useState } from "react";
import { caseApi } from "../api";
import type { Job } from "../api/types";

/** Poll cadence per spec/backend.md B9 / spec/frontend.md F4: 2s initially, 5s after 30s. */
const INITIAL_INTERVAL_MS = 2_000;
const BACKOFF_INTERVAL_MS = 5_000;
const BACKOFF_AFTER_MS = 30_000;

/**
 * PROVISIONAL (B9 gap): frontend.md only says "After a UI wait threshold,
 * display 'Still processing'" without naming the threshold. Chosen as a
 * sensible constant; logged in spec/progress.md B9 gaps.
 */
export const STILL_PROCESSING_THRESHOLD_MS = 90_000;

export interface JobPollingState {
  job: Job | null;
  /** True once polling has run past STILL_PROCESSING_THRESHOLD_MS without a terminal status. */
  stillProcessing: boolean;
  /** True while the most recent poll failed at the transport level; polling keeps going (frontend.md F4). */
  transientError: boolean;
}

interface UseJobPollingOptions {
  /** Job to poll; passing null stops polling. */
  jobId: string | null;
  onSucceeded: (job: Job) => void;
  onFailed: (job: Job) => void;
  onSuperseded: (job: Job) => void;
}

/**
 * Polls `GET /jobs/{id}` at the spec's cadence, stopping on any terminal
 * status or on unmount/`jobId` change. A transport error never claims the
 * server job failed — it shows a transient notice and keeps polling with
 * backoff (frontend.md F4: "A transport error stops neither the server job
 * nor its stored progress").
 */
export function useJobPolling({ jobId, onSucceeded, onFailed, onSuperseded }: UseJobPollingOptions): JobPollingState {
  const [state, setState] = useState<JobPollingState>({ job: null, stillProcessing: false, transientError: false });
  const callbacksRef = useRef({ onSucceeded, onFailed, onSuperseded });
  useEffect(() => {
    callbacksRef.current = { onSucceeded, onFailed, onSuperseded };
  });

  useEffect(() => {
    if (!jobId) {
      setState({ job: null, stillProcessing: false, transientError: false });
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const startedAt = Date.now();

    function scheduleNext(elapsedMs: number): void {
      const interval = elapsedMs >= BACKOFF_AFTER_MS ? BACKOFF_INTERVAL_MS : INITIAL_INTERVAL_MS;
      timer = setTimeout(() => void poll(), interval);
    }

    async function poll(): Promise<void> {
      if (cancelled) return;
      const elapsedMs = Date.now() - startedAt;
      const stillProcessing = elapsedMs >= STILL_PROCESSING_THRESHOLD_MS;
      try {
        const job = await caseApi.getJob(jobId as string);
        if (cancelled) return;
        setState({ job, stillProcessing, transientError: false });
        if (job.status === "succeeded") {
          callbacksRef.current.onSucceeded(job);
          return;
        }
        if (job.status === "failed") {
          callbacksRef.current.onFailed(job);
          return;
        }
        if (job.status === "superseded") {
          callbacksRef.current.onSuperseded(job);
          return;
        }
        scheduleNext(elapsedMs);
      } catch {
        if (cancelled) return;
        setState((prev) => ({ ...prev, transientError: true, stillProcessing }));
        // A transport error always backs off to the slower cadence, regardless
        // of elapsed time, rather than hammering an already-struggling connection.
        timer = setTimeout(() => void poll(), BACKOFF_INTERVAL_MS);
      }
    }

    void poll();

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  return state;
}
