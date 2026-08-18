"use client";

import { useState } from "react";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { WatchlistRow } from "./WatchlistRow";
import { Button } from "../ui/Button";

export function WatchlistPanel() {
  const tickers = useWatchlistStore((s) => s.tickers);
  const cap = useWatchlistStore((s) => s.cap);
  const error = useWatchlistStore((s) => s.error);
  const add = useWatchlistStore((s) => s.add);
  const clearError = useWatchlistStore((s) => s.clearError);
  const [draft, setDraft] = useState("");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const value = draft.trim();
    if (!value) return;
    if (await add(value)) setDraft("");
  }

  return (
    <section className="panel flex min-h-0 flex-col" aria-label="Watchlist">
      <header className="panel-title flex items-center justify-between">
        <span>Watchlist</span>
        <span className="text-flat normal-case tracking-normal">
          {tickers.length}/{cap}
        </span>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="watchlist">
        {tickers.map((ticker) => (
          <WatchlistRow key={ticker} ticker={ticker} />
        ))}
        {tickers.length === 0 && (
          <p className="px-3 py-6 text-center text-xs text-text-muted">Watchlist is empty.</p>
        )}
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-border p-2">
        <input
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value.toUpperCase());
            if (error) clearError();
          }}
          placeholder="ADD TICKER"
          maxLength={5}
          aria-label="Add ticker to watchlist"
          data-testid="add-ticker-input"
          className="min-w-0 flex-1 rounded border border-border bg-bg px-2 py-1 text-xs uppercase tracking-wider text-text placeholder:text-flat focus:border-blue focus:outline-none"
        />
        <Button type="submit" variant="ghost" data-testid="add-ticker-submit">
          Add
        </Button>
      </form>

      {error && (
        <p
          role="alert"
          data-testid="watchlist-error"
          className="border-t border-border px-3 py-2 text-xs text-down-text"
        >
          {error}
        </p>
      )}
    </section>
  );
}
