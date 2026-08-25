/**
 * Fetch wrapper that understands the API's single error envelope:
 * {"error": {"code", "message"}} on every failure.
 */

export class ApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * How long a request may run before it is abandoned.
 *
 * A request that never settles is worse than one that fails: nothing
 * downstream can tell it apart from work still in progress. Vercel kills the
 * function at 60s, but the browser keeps a pending promise until then -- which
 * is how a cold Neon instance held the boot screen up for a full minute.
 * Comfortably above a healthy round trip, comfortably below the platform's own
 * limit, so the client is what gives up first and can say why.
 */
export const DEFAULT_TIMEOUT_MS = 20_000;

/** Slow by design: the LLM round trip, which must not be cut off at 20s. */
export const CHAT_TIMEOUT_MS = 45_000;

export interface RequestOptions {
  timeoutMs?: number;
}

/**
 * Whether a thrown value is the deadline firing rather than a real failure.
 *
 * `AbortSignal.timeout` aborts with a TimeoutError; a caller's own abort
 * arrives as an AbortError. Both mean the request ran out of time rather than
 * the server being down, and the two need different words from a genuine
 * network failure: one says "try again", the other says "check your
 * connection".
 */
function isTimeout(error: unknown): boolean {
  const name = (error as { name?: string } | null)?.name;
  return name === "TimeoutError" || name === "AbortError";
}

const timeoutError = () =>
  new ApiError("TIMEOUT", "The server took too long to respond.", 0);

async function request<T>(
  path: string,
  init?: RequestInit,
  { timeoutMs = DEFAULT_TIMEOUT_MS }: RequestOptions = {},
): Promise<T> {
  // Live for the whole response lifecycle, body streaming included -- which
  // is why every read below is guarded too, not just this call. A deadline
  // that fires after the headers arrive but mid-body would otherwise escape
  // as a raw DOMException, and every caller tests `instanceof ApiError`.
  const signal = AbortSignal.timeout(timeoutMs);

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (error) {
    if (isTimeout(error)) throw timeoutError();
    throw new ApiError("NETWORK_ERROR", "Could not reach the server.", 0);
  }

  if (!response.ok) {
    let code = "INTERNAL_ERROR";
    let message = "Something went wrong.";
    try {
      const body = await response.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      }
    } catch (error) {
      // A non-JSON error body leaves the defaults in place -- but a deadline
      // firing mid-body is not a malformed body, and reporting it as
      // INTERNAL_ERROR would hide the one thing the caller could act on.
      if (isTimeout(error)) throw timeoutError();
    }
    throw new ApiError(code, message, response.status);
  }

  // A successful response with no body (an empty string, not malformed JSON)
  // is a real shape a route can send -- and `.json()` throws a raw
  // `SyntaxError` on it that this function's own error handling above never
  // sees, because it happens after the `!response.ok` branch. Reading the
  // text first and only parsing when there is any lets that case return
  // `undefined` instead of throwing. A non-empty body that fails to parse
  // still throws -- that's a real bug in a response, not an empty one, and
  // hiding it here would be worse than the exception.
  let text: string;
  try {
    text = await response.text();
  } catch (error) {
    if (isTimeout(error)) throw timeoutError();
    throw new ApiError("NETWORK_ERROR", "The response could not be read.", response.status);
  }
  return (text === "" ? undefined : JSON.parse(text)) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }, options),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { method: "DELETE" }, options),
};
