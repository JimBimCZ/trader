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
