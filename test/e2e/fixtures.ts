import { test as base, expect, type Page } from "@playwright/test";

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
    // The watchlist is the first thing to render from real data.
    await expect(page.getByTestId("watchlist-row-AAPL")).toBeVisible();
    await use(page);
  },
});

export { expect };

/** Waits until a live price has arrived for a ticker. */
export async function waitForPrice(page: Page, ticker: string) {
  await expect(page.getByTestId(`price-${ticker}`)).not.toHaveText("—", { timeout: 15_000 });
}
