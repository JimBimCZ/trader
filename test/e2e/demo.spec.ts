import { test, expect, goToPortfolio } from "./fixtures";

/**
 * The one scenario that needs the demo on. Every other spec in this suite
 * runs against docker-compose.test.yml's default DEMO_PORTFOLIO=false, so
 * their fresh-start assertions ($10,000, no positions) keep meaning what
 * they were written to mean. This one is meaningless against that stack --
 * a fresh guest there opens on cash alone -- so it skips itself unless the
 * stack was started with the flag flipped:
 *
 *   DEMO_PORTFOLIO=true docker compose -f docker-compose.test.yml up -d --build
 *   DEMO_PORTFOLIO=true npx playwright test demo.spec.ts
 *
 * `app`'s POST /api/reset (fixtures.ts) is what actually seeds the demo: a
 * fresh cookie-less request mints a guest, and ResetService re-seeds a guest
 * with the demo whenever settings.demo_portfolio is true -- which it is on
 * this stack, and isn't on the one every other spec runs against.
 */
test.describe("Demo portfolio", () => {
  test.skip(
    process.env.DEMO_PORTFOLIO !== "true",
    "only meaningful against a stack started with DEMO_PORTFOLIO=true",
  );

  test("first load shows the seeded holdings, a real performance chart, and a real history", async ({
    app,
  }) => {
    await goToPortfolio(app);

    for (const ticker of ["AAPL", "MSFT", "NVDA", "TSLA"]) {
      await expect(app.getByTestId(`position-${ticker}`)).toBeVisible();
    }

    // A fresh, undemoed portfolio renders this copy instead of a chart; the
    // backfilled curve means the demo never shows it.
    await expect(app.getByTestId("pnl-chart")).not.toContainText("Charting starts");

    await app.getByRole("link", { name: "History" }).click();
    await expect(app.getByTestId("trade-history").locator("tbody tr")).toHaveCount(4);
  });
});
