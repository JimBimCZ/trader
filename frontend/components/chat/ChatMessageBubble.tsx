"use client";

import type { ChatMessage } from "@/lib/types";
import { formatPrice, formatQuantity } from "@/lib/format";
import { TickerChip } from "../ui/TickerChip";

const VERBS: Record<string, { attempted: string; done: string }> = {
  buy: { attempted: "Buy", done: "Bought" },
  sell: { attempted: "Sell", done: "Sold" },
  add: { attempted: "Add", done: "Added" },
  remove: { attempted: "Remove", done: "Removed" },
};

/** A rejected action never happened, so it is named by the attempt. */
function actionLabel(action: ChatMessage["actions"] extends (infer T)[] | null ? T : never) {
  const done = action.status === "ok";
  const isTrade = action.kind === "trade";
  const key = String((isTrade ? action.detail.side : action.detail.action) ?? "");
  const verb = VERBS[key]?.[done ? "done" : "attempted"] ?? key;

  if (!isTrade) return `${verb} ${action.ticker}`;

  const quantity = Number(action.detail.quantity ?? 0);
  const price = action.detail.price;
  const at = done && typeof price === "number" ? ` at ${formatPrice(price)}` : "";
  return `${verb} ${formatQuantity(quantity)} ${action.ticker}${at}`;
}

export function ChatMessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={isUser ? "flex flex-col items-end" : "flex flex-col items-start"} data-testid={`chat-${message.role}`}>
      <div
        className={`max-w-[92%] whitespace-pre-wrap px-3.5 py-2 text-[13px] leading-[1.45] ${
          isUser
            ? "rounded-[18px] rounded-br-[5px] bg-blue-fill text-white"
            : "rounded-[18px] rounded-bl-[5px] bg-surface-sunk text-text"
        }`}
      >
        {message.content}
      </div>

      {message.actions && message.actions.length > 0 && (
        <ul className="mt-2 w-full space-y-1.5" data-testid="chat-actions">
          {message.actions.map((action, index) => (
            <li
              key={index}
              className={`flex items-start gap-2 rounded-control px-2.5 py-2 text-[12px] ${
                action.status === "ok" ? "bg-up-wash text-up-text" : "bg-down-wash text-down-text"
              }`}
            >
              <TickerChip ticker={action.ticker} size="sm" />
              <span className="min-w-0">
                <span className="block font-semibold">{actionLabel(action)}</span>
                {action.status === "error" && action.errorMessage && (
                  <span className="block opacity-80">{action.errorMessage}</span>
                )}
              </span>
              <span className="ml-auto shrink-0 font-bold" aria-hidden="true">
                {action.status === "ok" ? "✓" : "✕"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
