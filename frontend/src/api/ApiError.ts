import type { ApiErrorBody, ApiErrorCode, FieldError } from "./types";

/** Typed error thrown by both CaseApi adapters for any non-2xx response. */
export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status: number;
  readonly fieldErrors: FieldError[];
  readonly retryable: boolean;

  constructor(status: number, body: ApiErrorBody) {
    super(body.error.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error.code;
    this.fieldErrors = body.error.field_errors;
    this.retryable = body.error.retryable;
  }
}
