"use client";

import { useEffect, useRef, useState } from "react";
import { useChatStore } from "@/store/useChatStore";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { Button } from "../ui/Button";

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

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const text = draft.trim();
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
        className="panel px-3 py-2 text-xs uppercase tracking-widest text-text-muted hover:text-text"
        data-testid="chat-expand"
      >
        Assistant
      </button>
    );
  }

  return (
    <section className="panel flex min-h-0 flex-1 flex-col" aria-label="AI assistant">
      <header className="panel-title flex items-center justify-between">
        <span>Assistant</span>
        <button
          onClick={() => setCollapsed(true)}
          className="normal-case tracking-normal text-flat hover:text-text"
          aria-label="Collapse assistant panel"
          data-testid="chat-collapse"
        >
          ×
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3" data-testid="chat-messages">
        {messages.length === 0 && (
          <p className="text-xs leading-relaxed text-text-muted">
            Ask about your portfolio, or tell me what to trade.
            <br />
            <span className="text-flat">Try “how is my portfolio doing?” or “buy 10 AAPL”.</span>
          </p>
        )}
        {messages.map((message) => (
          <ChatMessageBubble key={message.id} message={message} />
        ))}
        {isLoading && (
          <p className="text-xs text-text-muted" data-testid="chat-loading">
            <span className="inline-block animate-pulse">Thinking…</span>
          </p>
        )}
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-border p-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask or instruct…"
          aria-label="Message the assistant"
          data-testid="chat-input"
          className="min-w-0 flex-1 rounded border border-border bg-bg px-2 py-1.5 text-xs text-text placeholder:text-flat focus:border-blue focus:outline-none"
        />
        <Button type="submit" variant="submit" disabled={isLoading} data-testid="chat-send">
          Send
        </Button>
      </form>
    </section>
  );
}
