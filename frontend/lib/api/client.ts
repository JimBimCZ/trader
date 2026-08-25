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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
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
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
