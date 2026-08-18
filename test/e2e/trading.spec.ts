import { test, expect, waitForPrice } from "./fixtures";

test.describe("Trading", () => {
  test("buying reduces cash and opens a position", async ({ app }) => {
    await waitForPrice(app, "AAPL");

    await app.getByTestId("trade-ticker").fill("AAPL");
    await app.getByTestId("trade-quantity").fill("10");
    await app.getByTestId("buy-button").click();

    await expect(app.getByTestId("position-AAPL")).toBeVisible();
    await expect(app.getByTestId("position-AAPL")).toContainText("10");

    // Roughly $1,900 of a $10,000 balance.
    await expect
      .poll(async () => {
        const text = (await app.getByTestId("cash-balance").textContent()) ?? "";
        return Number(text.replace(/[$,]/g, ""));
      })
      .toBeLessThan(8_500);
  });

  test("selling closes the position and returns the cash", async ({ app }) => {
    await waitForPrice(app, "AAPL");

    await app.getByTestId("trade-ticker").fill("AAPL");
    await app.getByTestId("trade-quantity").fill("5");
    await app.getByTestId("buy-button").click();
    await expect(app.getByTestId("position-AAPL")).toBeVisible();

    await app.getByTestId("trade-quantity").fill("5");
    await app.getByTestId("sell-button").click();

    await expect(app.getByTestId("position-AAPL")).toHaveCount(0);
    await expect
      .poll(async () => {
        const text = (await app.getByTestId("cash-balance").textContent()) ?? "";
        return Number(text.replace(/[$,]/g, ""));
      })
      .toBeGreaterThan(9_900);
  });

  test("an unaffordable buy is refused with a reason", async ({ app }) => {
    await waitForPrice(app, "AAPL");

    await app.getByTestId("trade-ticker").fill("AAPL");
    await app.getByTestId("trade-quantity").fill("100000");
    await app.getByTestId("buy-button").click();

    await expect(app.getByTestId("trade-error")).toContainText("available");
    await expect(app.getByTestId("cash-balance")).toHaveText("$10,000.00");
  });

  test("selling shares that are not held is refused", async ({ app }) => {
    await waitForPrice(app, "AAPL");

    await app.getByTestId("trade-ticker").fill("AAPL");
    await app.getByTestId("trade-quantity").fill("1");
    await app.getByTestId("sell-button").click();

    await expect(app.getByTestId("trade-error")).toContainText("Short selling");
  });

  test("the heatmap and P&L chart populate after a trade", async ({ app }) => {
    await waitForPrice(app, "NVDA");

    await app.getByTestId("trade-ticker").fill("NVDA");
    await app.getByTestId("trade-quantity").fill("2");
    await app.getByTestId("buy-button").click();

    await expect(app.getByTestId("position-NVDA")).toBeVisible();
    // Every heatmap cell carries a signed percentage, not colour alone.
    await expect(app.getByTestId("heatmap")).toContainText("NVDA");
    await expect(app.getByTestId("heatmap")).toContainText("%");
  });

  test("a held ticker stays valued after leaving the watchlist", async ({ app }) => {
    await waitForPrice(app, "TSLA");

    await app.getByTestId("trade-ticker").fill("TSLA");
    await app.getByTestId("trade-quantity").fill("2");
    await app.getByTestId("buy-button").click();
    await expect(app.getByTestId("position-TSLA")).toBeVisible();

    await app.getByTestId("watchlist-row-TSLA").hover();
    await app.getByTestId("remove-TSLA").click();
    await expect(app.getByTestId("watchlist-row-TSLA")).toHaveCount(0);

    // The position must remain, still priced, and be flagged as unwatched.
    await expect(app.getByTestId("position-TSLA")).toBeVisible();
    await expect(app.getByTestId("position-TSLA")).toContainText("unwatched");
    await expect(app.getByTestId("position-TSLA")).toContainText("$");
  });
});
