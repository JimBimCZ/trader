"use client";

import type { ChatMessage } from "@/lib/types";
import { formatPrice, formatQuantity } from "@/lib/format";

function actionLabel(action: ChatMessage["actions"] extends (infer T)[] | null ? T : never) {
  if (action.kind === "trade") {
    const side = String(action.detail.side ?? "").toUpperCase();
    const quantity = Number(action.detail.quantity ?? 0);
    const price = action.detail.price;
    const at = typeof price === "number" ? ` @ ${formatPrice(price)}` : "";
    return `${side} ${formatQuantity(quantity)} ${action.ticker}${at}`;
  }
  const verb = action.detail.action === "add" ? "Added" : "Removed";
  return `${verb} ${action.ticker}`;
}

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={isUser ? "text-right" : "text-left"} data-testid={`chat-${message.role}`}>
      <div
        className={`inline-block max-w-[92%] whitespace-pre-wrap rounded px-2.5 py-1.5 text-left text-xs leading-relaxed ${
          isUser ? "bg-blue/15 text-text" : "bg-bg-raised text-text"
        }`}
      >
        {message.content}
      </div>

      {message.actions && message.actions.length > 0 && (
        <ul className="mt-1.5 space-y-1" data-testid="chat-actions">
          {message.actions.map((action, index) => (
            <li
              key={index}
              className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-[10px] uppercase tracking-wider ${
                action.status === "ok"
                  ? "border-up/40 bg-up/10 text-up-text"
                  : "border-down/40 bg-down/10 text-down-text"
              }`}
            >
              <span aria-hidden="true">{action.status === "ok" ? "✓" : "✕"}</span>
              <span>{actionLabel(action)}</span>
              {action.status === "error" && action.errorMessage && (
                <span className="normal-case tracking-normal opacity-80">
                  — {action.errorMessage}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
