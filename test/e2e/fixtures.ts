import { test as base, expect, type Page } from "@playwright/test";

export const BASE_URL = process.env.BASE_URL ?? "http://localhost:8000";

/**
 * The state a browser is in once the onboarding tour has been dismissed.
 *
 * The tour scrims the whole viewport for any guest who has not seen it,
 * and every test starts in a fresh context -- so without this, the scrim
 * intercepts every click in the suite. Applied once in playwright.config.ts
 * so contexts the fixtures build inherit it; auth.spec.ts builds its own
 * contexts by hand and passes it explicitly.
 */
export const tourDismissed = {
  cookies: [],
  origins: [
    { origin: BASE_URL, localStorage: [{ name: "trader-tour-seen", value: "1" }] },
  ],
};

/**
 * Every test starts from the seeded state.
 *
 * POST /api/reset exists partly for this: without it, tests would inherit
 * each other's positions and cash, and would only pass in one order.
 */
export const test = base.extend<{ app: Page }>({
  app: async ({ page, request }, use) => {
    await request.post("/api/reset");
    await page.goto("/");
    await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
    await use(page);
  },
});

export { expect };

/**
 * Closes the receipt a filled ticket trade raises.
 *
 * Every successful buy or sell from the trade ticket now opens a modal over
 * the workspace. Assertions still read straight through it, but any *click*
 * behind it is intercepted -- so a test that trades and then touches the page
 * again has to dismiss it, in the same way a person would.
 */
export async function dismissReceipt(page: Page) {
  await page.getByTestId("trade-receipt").getByRole("button", { name: "Done" }).click();
  await expect(page.getByTestId("trade-receipt")).toHaveCount(0);
}

/** Waits until a live price has arrived for a ticker. */
export async function waitForPrice(page: Page, ticker: string) {
  await expect(page.getByTestId(`price-${ticker}`)).not.toHaveText("—", { timeout: 15_000 });
}

/**
 * Navigates to /portfolio/ the way a person does now -- clicking the rail's
 * link, not a scroll target -- and confirms the rail marks it as the current
 * route. The heatmap, the performance chart and the positions table all live
 * here now, not on the overview.
 */
export async function goToPortfolio(page: Page) {
  const link = page.getByRole("link", { name: "Portfolio" });
  await link.click();
  await expect(link).toHaveAttribute("aria-current", "page");
}
