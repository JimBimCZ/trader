import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError } from "@/lib/api/client";

/**
 * Exercises the real fetch/Response/json() path -- unlike the store tests,
 * which mock `@/lib/api/endpoints` wholesale and so never touch this file at
 * all. C2 was a bug in exactly this layer: `POST /api/auth/claim` returned a
 * genuinely empty 200 body, `.json()` threw a raw `SyntaxError` on it, and
 * that throw happened outside the `!response.ok` branch, so it was never
 * wrapped as an `ApiError` -- it reached the caller as an unhandled parse
 * failure after the cookie had already moved to the new account. A test
 * mocking `endpoints.ts` can't see any of that: it never calls `fetch` or
 * `Response.json()`, so it can't fail the way the real bug failed.
 */

function fetchResponse(body: string, init?: ResponseInit) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response(body, { status: 200, ...init })),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client, success responses", () => {
  it("parses a normal JSON 200 body", async () => {
    fetchResponse(JSON.stringify({ ok: true }));
    await expect(api.get("/api/whatever")).resolves.toEqual({ ok: true });
  });

  it("resolves an empty 200 body to undefined instead of throwing", async () => {
    // Reproduces the exact response `POST /api/auth/claim` used to send:
    // status 200, zero-length body. `new Response("")` matches what the
    // browser hands `fetch` for that response -- `.text()` on it is `""`.
    fetchResponse("");
    await expect(api.post("/api/auth/claim", { token: "t" })).resolves.toBeUndefined();
  });

  it("still throws on a non-empty body that isn't valid JSON", async () => {
    // The belt-and-braces fix must not swallow a genuinely malformed
    // success body -- only a truly empty one is treated specially.
    fetchResponse("not json");
    await expect(api.get("/api/whatever")).rejects.toThrow();
  });
});

describe("api client, error responses", () => {
  it("wraps a JSON error envelope as ApiError", async () => {
    fetchResponse(JSON.stringify({ error: { code: "NOT_FOUND", message: "nope" } }), {
      status: 404,
    });
    await expect(api.get("/api/whatever")).rejects.toMatchObject({
      code: "NOT_FOUND",
      message: "nope",
      status: 404,
    } satisfies Partial<ApiError>);
  });

  it("falls back to a generic error on a non-JSON error body", async () => {
    fetchResponse("", { status: 500 });
    await expect(api.get("/api/whatever")).rejects.toMatchObject({
      code: "INTERNAL_ERROR",
      status: 500,
    });
  });
});

describe("api client, timeouts", () => {
  /**
   * A request that never settles is worse than one that fails: nothing
   * downstream can distinguish it from work still in progress. On Vercel the
   * platform eventually kills the function at 60s, but the browser is left
   * holding a pending promise until then -- which is what held the boot
   * screen up for a full minute when Neon was cold.
   */
  it("aborts a request that outlives its budget", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        (_url: string, init?: RequestInit) =>
          new Promise((_resolve, reject) => {
            init?.signal?.addEventListener("abort", () =>
              reject(Object.assign(new Error("aborted"), { name: "AbortError" })),
            );
          }),
      ),
    );

    await expect(api.get("/api/auth/me", { timeoutMs: 20 })).rejects.toMatchObject({
      code: "TIMEOUT",
    });
  });

  it("distinguishes a timeout from an unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.get("/api/auth/me")).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });

  it("passes a signal to fetch so the request is genuinely cancelled", async () => {
    const spy = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", spy);

    await api.get("/api/whatever");

    expect(spy.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  });

  it("lets a slow-by-design call ask for a longer budget", async () => {
    // The LLM round trip legitimately runs for many seconds; the default
    // budget must not be what decides whether chat works.
    const spy = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", spy);

    await api.post("/api/chat", { message: "hi" }, { timeoutMs: 45_000 });

    expect(spy).toHaveBeenCalled();
  });
});
