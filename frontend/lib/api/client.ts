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

async function request<T>(
  path: string,
  init?: RequestInit,
  { timeoutMs = DEFAULT_TIMEOUT_MS }: RequestOptions = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      signal: AbortSignal.timeout(timeoutMs),
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (error) {
    // A timeout and an unreachable server both surface here, and they need
    // different words: one means "try again", the other means "check your
    // connection". `AbortSignal.timeout` aborts with a TimeoutError, but a
    // caller's own abort arrives as AbortError, so both are treated as the
    // request having run out of time rather than the server being down.
    const name = (error as { name?: string })?.name;
    if (name === "TimeoutError" || name === "AbortError") {
      throw new ApiError("TIMEOUT", "The server took too long to respond.", 0);
    }
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
    } catch {
      // A non-JSON error body leaves the defaults in place.
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
  const text = await response.text();
  return (text === "" ? undefined : JSON.parse(text)) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, undefined, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }, options),
  delete: <T>(path: string, options?: RequestOptions) =>
    request<T>(path, { method: "DELETE" }, options),
};
