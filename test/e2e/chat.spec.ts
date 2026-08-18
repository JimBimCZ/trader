import { test, expect, waitForPrice } from "./fixtures";

// The backend runs with LLM_MOCK=true, so every response here follows the
// table in API_CONTRACT §9.
test.describe("AI assistant", () => {
  test("answers a portfolio question with real figures", async ({ app }) => {
    await app.getByTestId("chat-input").fill("how is my portfolio doing?");
    await app.getByTestId("chat-send").click();

    await expect(app.getByTestId("chat-user").last()).toContainText("how is my portfolio");
    await expect(app.getByTestId("chat-assistant").last()).toContainText("$10,000.00");
  });

  test("executes a trade and shows it inline", async ({ app }) => {
    await waitForPrice(app, "AAPL");

    await app.getByTestId("chat-input").fill("buy 10 shares of AAPL");
    await app.getByTestId("chat-send").click();

    await expect(app.getByTestId("chat-actions").last()).toContainText("BUY 10 AAPL");
    await expect(app.getByTestId("position-AAPL")).toBeVisible();
  });

  test("manages the watchlist", async ({ app }) => {
    await app.getByTestId("chat-input").fill("add PYPL to my watchlist");
    await app.getByTestId("chat-send").click();

    await expect(app.getByTestId("chat-actions").last()).toContainText("Added PYPL");
    await expect(app.getByTestId("watchlist-row-PYPL")).toBeVisible();
  });

  test("reports a rejected trade rather than failing silently", async ({ app }) => {
    await waitForPrice(app, "AAPL");

    await app.getByTestId("chat-input").fill("buy 100000 AAPL");
    await app.getByTestId("chat-send").click();

    await expect(app.getByTestId("chat-actions").last()).toContainText("available");
    await expect(app.getByTestId("cash-balance")).toHaveText("$10,000.00");
  });

  test("an upstream failure stays inside the conversation", async ({ app }) => {
    await app.getByTestId("chat-input").fill("__mock_error__");
    await app.getByTestId("chat-send").click();

    await expect(app.getByTestId("chat-assistant").last()).toContainText("trouble reaching");
  });

  test("history survives a reload", async ({ app }) => {
    await app.getByTestId("chat-input").fill("hello there");
    await app.getByTestId("chat-send").click();
    await expect(app.getByTestId("chat-assistant").last()).toBeVisible();

    await app.reload();
    await expect(app.getByTestId("chat-user").first()).toContainText("hello there");
  });
});
