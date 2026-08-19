import { test, expect, waitForPrice } from "./fixtures";

test.describe("Fresh start", () => {
  test("shows the default watchlist, $10k, and streaming prices", async ({ app }) => {
    for (const ticker of ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "JPM", "V", "NFLX"]) {
      await expect(app.getByTestId(`watchlist-row-${ticker}`)).toBeVisible();
    }

    await expect(app.getByTestId("cash-balance")).toHaveText("$10,000.00");
    await expect(app.getByTestId("total-value")).toHaveText("$10,000.00");

    await waitForPrice(app, "AAPL");
    await expect(app.getByTestId("connection-status")).toHaveAttribute("data-status", "open");
  });

  test("prices update over the stream", async ({ app }) => {
    await waitForPrice(app, "AAPL");
    const first = await app.getByTestId("price-AAPL").textContent();

    // The simulator is seeded, so movement is deterministic but still needs a
    // few ticks to exceed the cent the display rounds to.
    await expect
      .poll(async () => app.getByTestId("price-AAPL").textContent(), { timeout: 20_000 })
      .not.toBe(first);
  });

  test("the main chart renders for the selected ticker", async ({ app }) => {
    await expect(app.getByTestId("main-chart")).toBeVisible();
    await expect(app.getByTestId("main-chart").locator("canvas").first()).toBeVisible();
  });
});

test.describe("Watchlist", () => {
  test("adds and removes a ticker", async ({ app }) => {
    await app.getByTestId("add-ticker-input").fill("PYPL");
    await app.getByTestId("add-ticker-submit").click();
    await expect(app.getByTestId("watchlist-row-PYPL")).toBeVisible();

    await app.getByTestId("watchlist-row-PYPL").hover();
    await app.getByTestId("remove-PYPL").click();
    await expect(app.getByTestId("watchlist-row-PYPL")).toHaveCount(0);
  });

  test("rejects an invalid ticker with a readable message", async ({ app }) => {
    await app.getByTestId("add-ticker-input").fill("BRKB1");
    await app.getByTestId("add-ticker-submit").click();
    await expect(app.getByTestId("watchlist-error")).toContainText("valid ticker");
  });

  test("selecting a ticker changes the chart", async ({ app }) => {
    await app.getByTestId("select-MSFT").click();
    await expect(app.getByRole("region", { name: "Price chart" })).toContainText("MSFT");
  });
});
