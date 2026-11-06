/**
 * Server errors → words the user can read, in the current language.
 *
 * The API client throws `ApiError` with the HTTP status and, when the body is
 * JSON, the backend's `detail` (a string, or `{code, message}`). A backend
 * `code` with a matching `error.code.<code>` key wins; otherwise the status
 * picks a key from STATUS_KEYS. The backend detail is appended for statuses
 * where it helps (a bad schedule, a Telegram API refusal) and left out for
 * sign-in refusals, which stay generic on purpose (SECURITY-REVIEW.md).
 */

import { t } from "./i18n";

export class ApiError extends Error {
  constructor(
    readonly path: string,
    readonly status: number,
    readonly detail: string | null = null,
    readonly code: string | null = null,
  ) {
    // The English technical form stays in `message` for logs and tests.
    super(`${path} ${status}: ${detail ?? ""}`.trimEnd());
    this.name = "ApiError";
  }
}

/** Status → language key; the first matching rule wins. */
export const STATUS_KEYS: { match: (status: number) => boolean; key: string }[] = [
  { match: (s) => s === 400 || s === 422, key: "error.badRequest" },
  { match: (s) => s === 401, key: "error.sessionExpired" },
  { match: (s) => s === 403, key: "error.forbidden" },
  { match: (s) => s === 404, key: "error.notFound" },
  { match: (s) => s === 429, key: "error.rateLimited" },
  { match: (s) => s === 501, key: "error.unsupported" },
  { match: (s) => s >= 502 && s <= 504, key: "error.unavailable" },
  { match: (s) => s >= 500, key: "error.server" },
];

/** Statuses whose backend detail is never shown (sign-in stays generic). */
export const HIDDEN_DETAIL = new Set([401, 403, 429]);
export const DETAIL_MAX = 200;

/** Read an error body: `{detail: "…"}` or `{detail: {code, message}}`. Non-JSON bodies give nothing. */
export async function apiErrorFrom(path: string, res: Response): Promise<ApiError> {
  let detail: string | null = null;
  let code: string | null = null;
  try {
    const body = (await res.json()) as { detail?: unknown };
    const d = body?.detail;
    if (typeof d === "string") detail = d;
    else if (d && typeof d === "object") {
      const o = d as Record<string, unknown>;
      if (typeof o.code === "string") code = o.code;
      if (typeof o.message === "string") detail = o.message;
    }
  } catch {
    /* not JSON (proxy page, empty body): the status alone decides */
  }
  return new ApiError(path, res.status, detail, code);
}

export function errorKey(e: ApiError): string {
  if (e.code) {
    const key = `error.code.${e.code}`;
    if (t(key) !== key) return key;
  }
  return STATUS_KEYS.find((r) => r.match(e.status))?.key ?? "error.generic";
}

/** One readable sentence for anything a request can throw. */
export function errorText(e: unknown): string {
  if (e instanceof ApiError) {
    const message = t(errorKey(e), { status: e.status });
    const detail = e.detail?.trim();
    if (!detail || HIDDEN_DETAIL.has(e.status)) return message;
    const short = detail.length > DETAIL_MAX ? `${detail.slice(0, DETAIL_MAX)}…` : detail;
    return t("error.withDetail", { message, detail: short });
  }
  // fetch() rejects with a TypeError when the network or the server is unreachable.
  if (e instanceof TypeError) return t("error.network");
  if (e instanceof Error) return e.message;
  return String(e);
}
