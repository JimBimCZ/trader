"use client";

import { useEffect, useRef, useState } from "react";
import { useChatStore } from "@/store/useChatStore";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { Button } from "../ui/Button";
import { CloseIcon } from "../ui/icons";
import { PANELS } from "../layout/panels";

const PROMPTS = ["How is my portfolio doing?", "Buy 10 AAPL", "What should I trim?"];

/** The assistant's mark, standing in for the instrument chips beside it. */
function AiAvatar({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <span
      className={`flex items-center justify-center rounded-full bg-brand text-[11px] font-bold text-white ${className}`}
    >
      AI
    </span>
  );
}

export function ChatPanel() {
  const messages = useChatStore((s) => s.messages);
  const isLoading = useChatStore((s) => s.isLoading);
  const send = useChatStore((s) => s.send);
  const refreshPortfolio = usePortfolioStore((s) => s.refresh);
  const refreshWatchlist = useWatchlistStore((s) => s.refresh);

  const [draft, setDraft] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, isLoading]);

  async function dispatch(text: string) {
    if (!text || isLoading) return;
    setDraft("");
    await send(text);
    // The assistant may have traded or changed the watchlist, so pull the
    // authoritative state rather than guessing at it.
    await Promise.all([refreshPortfolio(), refreshWatchlist()]);
  }

  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="card flex items-center gap-2 px-4 py-3 font-display text-[13px] font-bold tracking-tight text-text hover:bg-surface-alt"
        data-testid="chat-expand"
      >
        <AiAvatar className="h-6 w-6" />
        Assistant
      </button>
    );
  }

  return (
    <section
      id={PANELS.assistant.id}
      className="rise card flex min-h-[340px] flex-1 flex-col lg:min-h-0"
      aria-label="AI assistant"
    >
      <header className="card-title">
        <span className="flex items-center gap-2.5">
          <AiAvatar />
          <span>
            <span className="block">Assistant</span>
            <span className="block font-sans text-[11px] font-normal text-text-muted">
              Trades on your say-so
            </span>
          </span>
        </span>
        <button
          onClick={() => setCollapsed(true)}
          className="flex h-7 w-7 items-center justify-center rounded-full text-text-faint transition hover:bg-surface-sunk hover:text-text"
          aria-label="Collapse assistant panel"
          data-testid="chat-collapse"
        >
          <CloseIcon />
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-2" data-testid="chat-messages">
        {messages.length === 0 && (
          <div className="space-y-3 px-1 pt-2">
            <p className="text-[13px] leading-relaxed text-text-muted">
              Ask about your positions, or say what to trade and I&apos;ll place the order.
            </p>
            <div className="flex flex-wrap gap-1.5">
              {PROMPTS.map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => dispatch(prompt)}
                  className="rounded-full bg-surface-sunk px-3 py-1.5 text-[12px] font-medium text-text transition hover:bg-border"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((message) => (
          <ChatMessageBubble key={message.id} message={message} />
        ))}
        {isLoading && (
          <p
            className="w-fit animate-pulse rounded-2xl rounded-bl-md bg-surface-sunk px-3.5 py-2.5 text-[13px] text-text-muted"
            data-testid="chat-loading"
          >
            Thinking…
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          void dispatch(draft.trim());
        }}
        className="flex gap-2 border-t border-border p-3"
      >
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask or instruct…"
          aria-label="Message the assistant"
          data-testid="chat-input"
          className="field min-w-0 flex-1"
        />
        <Button type="submit" variant="submit" disabled={isLoading} data-testid="chat-send">
          Send
        </Button>
      </form>
    </section>
  );
}
