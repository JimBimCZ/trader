"use client";

import { useState } from "react";

/**
 * What a panel shows when its data was asked for and the asking failed.
 *
 * The third state. A skeleton here would never resolve, and the panel's empty
 * copy ("No open positions") would assert something nobody managed to read.
 * This says what happened and offers the one action that can change it.
 */
export function LoadFailure({
  what,
  onRetry,
  className = "",
}: {
  /** Names the data, e.g. "the watchlist" -- reads as "Couldn't load ...". */
  what: string;
  onRetry: () => Promise<unknown>;
  className?: string;
}) {
  const [retrying, setRetrying] = useState(false);

  async function retry() {
    setRetrying(true);
    try {
      // The store records the outcome; a second failure just lands back here,
      // so nothing is gained by surfacing this rejection again.
      await onRetry().catch(() => {});
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div
      role="status"
      data-testid="load-failure"
      className={`flex flex-col items-center justify-center gap-2 px-4 py-6 text-center ${className}`}
    >
      <p className="text-[13px] text-text-muted">Couldn&apos;t load {what}.</p>
      <button
        type="button"
        onClick={retry}
        disabled={retrying}
        className="rounded-control bg-surface-sunk px-3 py-1.5 text-[12px] font-semibold text-text transition hover:opacity-80 active:opacity-70 disabled:opacity-50"
      >
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </div>
  );
}
