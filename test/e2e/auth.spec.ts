import { expect, test } from "@playwright/test";
import { dismissReceipt, goToPortfolio, tourDismissed } from "./fixtures";

test.describe("guest sessions", () => {
  test("two browsers get two portfolios", async ({ browser }) => {
    // The property the whole per-user phase exists for, asserted through the
    // UI rather than the API: separate contexts mean separate cookie jars.
    // browser.newContext() ignores the config's `use`, so the tour scrim has
    // to be dismissed here by hand.
    const first = await browser.newContext({ storageState: tourDismissed });
    const second = await browser.newContext({ storageState: tourDismissed });

    const a = await first.newPage();
    await a.goto("/");
    await a.getByTestId("trade-ticker").fill("AAPL");
    await a.getByTestId("trade-quantity").fill("2");
    await a.getByTestId("buy-button").click();
    await dismissReceipt(a);
    await goToPortfolio(a);
    await expect(a.getByTestId("position-AAPL")).toBeVisible();

    const b = await second.newPage();
    await b.goto("/portfolio/");
    await expect(b.getByTestId("position-AAPL")).toHaveCount(0);

    await first.close();
    await second.close();
  });

  test("a portfolio survives a reload", async ({ page }) => {
    await page.goto("/");
    await page.getByTestId("trade-ticker").fill("MSFT");
    await page.getByTestId("trade-quantity").fill("1");
    await page.getByTestId("buy-button").click();
    await dismissReceipt(page);

    await goToPortfolio(page);
    await expect(page.getByTestId("position-MSFT")).toBeVisible();

    await page.reload();
    await expect(page.getByTestId("position-MSFT")).toBeVisible();
  });
});

test.describe("sign-in", () => {
  test("no providers configured means no sign-in control", async ({ page }) => {
    // The E2E stack sets no OAuth credentials, which is also the quick start's
    // configuration -- so this asserts the zero-config path stays clean.
    // AccountMenu renders nothing at all when signed out with no providers
    // (see frontend/components/layout/AccountMenu.tsx), so there is no
    // "Sign in" button anywhere on the page.
    await page.goto("/");
    await expect(page.getByRole("button", { name: /sign in/i })).toHaveCount(0);
  });

  test("dev-login moves the session to another user", async ({ page }) => {
    // page.request shares the browser context's cookie jar with page.goto,
    // so every call here goes through it to stay talking to the same
    // session -- but the session itself is established through page.request
    // alone, never page.goto("/"): the SPA fetches /api/auth/me on mount too,
    // and against a cookie-less context that in-page fetch races an explicit
    // one issued right after goto() resolves, non-deterministically minting
    // two different guests and leaving whichever Set-Cookie lands last. The
    // dev-login redirect itself is safe to reach by navigation, because by
    // the time the SPA's own mount fetch fires the cookie it re-reads is
    // already the one the redirect just set.
    const original = (await (await page.request.get("/api/auth/me")).json()).id;

    await page.request.post("/api/auth/logout");
    const replacement = (await (await page.request.get("/api/auth/me")).json()).id;
    expect(replacement).not.toBe(original);

    await page.goto(`/api/auth/dev-login/${original}`);
    const restored = (await (await page.request.get("/api/auth/me")).json()).id;
    expect(restored).toBe(original);
  });
});
