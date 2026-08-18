import { test, expect, waitForPrice } from "./fixtures";

test.describe("Stream resilience", () => {
  test("reports a dropped stream and recovers on its own", async ({ app }) => {
    await waitForPrice(app, "AAPL");
    await expect(app.getByTestId("connection-status")).toHaveAttribute("data-status", "open");

    // Failing the request is deterministic. Going offline at the browser
    // level leaves the socket open, so EventSource never fires an error and
    // nothing would be observable here.
    let blocking = true;
    await app.route("**/api/stream/prices", async (route) => {
      if (blocking) await route.abort();
      else await route.fallback();
    });

    await app.evaluate(() => window.dispatchEvent(new Event("offline")));
    await app.reload();

    await expect(app.getByTestId("connection-status")).not.toHaveAttribute("data-status", "open", {
      timeout: 20_000,
    });

    // EventSource retries on its own schedule using the server's retry
    // directive, with no reload needed.
    blocking = false;
    await expect(app.getByTestId("connection-status")).toHaveAttribute("data-status", "open", {
      timeout: 30_000,
    });
  });

  test("state survives a reload", async ({ app }) => {
    await waitForPrice(app, "MSFT");

    await app.getByTestId("trade-ticker").fill("MSFT");
    await app.getByTestId("trade-quantity").fill("1");
    await app.getByTestId("buy-button").click();
    await expect(app.getByTestId("position-MSFT")).toBeVisible();

    await app.reload();
    await expect(app.getByTestId("position-MSFT")).toBeVisible();
  });
});
