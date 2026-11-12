import { HttpErrorResponse } from '@angular/common/http';

/** Human-readable message from a backend error ({detail: string | validation list}). */
export function apiErrorMessage(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (!(err instanceof HttpErrorResponse)) return fallback;
  if (err.status === 0) return 'Cannot reach the Noesis server. Is the backend running?';
  const detail = err.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  // No JSON detail on a 5xx usually means the dev proxy couldn't reach FastAPI.
  if (err.status >= 500) return 'The Noesis server is not responding or hit an error. Is the backend running?';
  return fallback;
}
