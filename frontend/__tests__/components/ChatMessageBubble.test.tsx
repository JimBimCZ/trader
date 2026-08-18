import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import type { ChatMessage } from "@/lib/types";

function message(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "1",
    role: "assistant",
    content: "Bought 10 AAPL.",
    actions: null,
    createdAt: "2026-08-18T09:00:00Z",
    ...overrides,
  };
}

describe("ChatMessageBubble", () => {
  it("renders the message text", () => {
    render(<ChatMessageBubble message={message()} />);
    expect(screen.getByText("Bought 10 AAPL.")).toBeInTheDocument();
  });

  it("distinguishes user messages from assistant messages", () => {
    render(<ChatMessageBubble message={message({ role: "user", content: "buy 10 AAPL" })} />);
    expect(screen.getByTestId("chat-user")).toBeInTheDocument();
  });

  it("renders an executed trade inline", () => {
    render(
      <ChatMessageBubble
        message={message({
          actions: [
            {
              kind: "trade",
              ticker: "AAPL",
              status: "ok",
              detail: { side: "buy", quantity: 10, price: 191.24 },
              errorCode: null,
              errorMessage: null,
            },
          ],
        })}
      />,
    );

    expect(screen.getByTestId("chat-actions")).toHaveTextContent("BUY 10 AAPL @ $191.24");
  });

  it("renders a rejected trade with its reason", () => {
    render(
      <ChatMessageBubble
        message={message({
          actions: [
            {
              kind: "trade",
              ticker: "AAPL",
              status: "error",
              detail: { side: "buy", quantity: 10000 },
              errorCode: "INSUFFICIENT_CASH",
              errorMessage: "Not enough cash.",
            },
          ],
        })}
      />,
    );

    const actions = screen.getByTestId("chat-actions");
    expect(actions).toHaveTextContent("Not enough cash.");
  });

  it("renders a watchlist change", () => {
    render(
      <ChatMessageBubble
        message={message({
          actions: [
            {
              kind: "watchlist",
              ticker: "PYPL",
              status: "ok",
              detail: { action: "add" },
              errorCode: null,
              errorMessage: null,
            },
          ],
        })}
      />,
    );

    expect(screen.getByTestId("chat-actions")).toHaveTextContent("Added PYPL");
  });

  it("renders no action list when there are none", () => {
    render(<ChatMessageBubble message={message({ actions: [] })} />);
    expect(screen.queryByTestId("chat-actions")).not.toBeInTheDocument();
  });
});
