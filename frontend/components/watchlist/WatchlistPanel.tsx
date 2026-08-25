"use client";

import { useState } from "react";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { WatchlistRow } from "./WatchlistRow";
import { Button } from "../ui/Button";
import { ErrorNote } from "../ui/ErrorNote";
import { SkeletonRow } from "../ui/Skeleton";
import { PANELS } from "../layout/panels";

export function WatchlistPanel() {
  const tickers = useWatchlistStore((s) => s.tickers);
  const cap = useWatchlistStore((s) => s.cap);
  const loaded = useWatchlistStore((s) => s.loaded);
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
    <section
      id={PANELS.watchlist.id}
      className="rise card flex max-h-[70vh] flex-1 flex-col overflow-hidden lg:max-h-none lg:min-h-0"
      aria-label="Watchlist"
    >
      <header className="card-title">
        <span>Watchlist</span>
        <span className="text-[11px] font-medium text-text-muted">
          {loaded ? `${tickers.length} of ${cap}` : "\u2014"}
        </span>
      </header>

      {/* No padding between rows, so the inset separators are what divide them. */}
      <div className="min-h-0 flex-1 overflow-y-auto" data-testid="watchlist">
        {tickers.map((ticker) => (
          <WatchlistRow key={ticker} ticker={ticker} />
        ))}
        {/* The empty copy is a claim about the list, so it waits until the
            list has actually been fetched. */}
        {!loaded &&
          Array.from({ length: 8 }, (_, i) => <SkeletonRow key={`skeleton-${i}`} />)}
        {loaded && tickers.length === 0 && (
          <p className="px-4 py-8 text-center text-[13px] text-text-muted">
            Nothing on the list yet. Add a symbol below to start watching it.
          </p>
        )}
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t-hairline border-border p-3">
        <input
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value.toUpperCase());
            if (error) clearError();
          }}
          placeholder="Add a symbol"
          maxLength={5}
          aria-label="Add ticker to watchlist"
          data-testid="add-ticker-input"
          className="field min-w-0 flex-1 uppercase tracking-wide placeholder:normal-case placeholder:tracking-normal"
        />
        <Button type="submit" variant="tinted" data-testid="add-ticker-submit">
          Add
        </Button>
      </form>

      {error && (
        <ErrorNote testId="watchlist-error" className="mx-3 mb-3">
          {error}
        </ErrorNote>
      )}
    </section>
  );
}
