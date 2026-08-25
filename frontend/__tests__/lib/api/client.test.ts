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
