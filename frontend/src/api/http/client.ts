import { ApiError } from "../ApiError";
import type { ApiErrorBody } from "../types";

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
}

/**
 * Thin fetch wrapper against relative `/api` (same origin as the Vite proxy
 * target, so cookies and CSRF behave — local-dev.md L1). Holds the CSRF token
 * handed back by login/me and attaches it to mutating requests.
 */
export class HttpClient {
  private csrfToken: string | null = null;

  setCsrfToken(token: string | null): void {
    this.csrfToken = token;
  }

  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const method = options.method ?? "GET";
    const headers: Record<string, string> = { Accept: "application/json", ...options.headers };

    let body: BodyInit | undefined;
    if (options.body instanceof FormData) {
      body = options.body;
    } else if (options.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(options.body);
    }

    if (method !== "GET" && this.csrfToken) {
      // PROVISIONAL (B9 gap): B9 requires a CSRF header on mutations but does
      // not name it.
      headers["X-CSRF-Token"] = this.csrfToken;
    }

    const response = await fetch(`/api${path}`, { method, headers, body, credentials: "same-origin" });

    if (response.status === 204) return undefined as T;

    const text = await response.text();
    const data: unknown = text ? JSON.parse(text) : undefined;

    if (!response.ok) {
      throw new ApiError(response.status, data as ApiErrorBody);
    }
    return data as T;
  }
}

/**
 * PROVISIONAL (B9 gap): B9 requires an Idempotency-Key header on
 * analyses/exports/submissions but does not name it.
 */
export const IDEMPOTENCY_HEADER = "Idempotency-Key";
