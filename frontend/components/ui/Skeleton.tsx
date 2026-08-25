/**
 * A placeholder for content that has been asked for but has not arrived.
 *
 * This exists because the panels had no third state: they distinguished
 * "has data" from "empty" and nothing else, so a slow load rendered the empty
 * copy -- "No open positions", "Positions appear here" -- as a statement of
 * fact about a portfolio nobody had fetched yet. A skeleton is the honest
 * answer to "what is here?" while the answer is still in flight.
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return <span aria-hidden="true" className={`skeleton block rounded-[6px] ${className}`} />;
}

/**
 * A skeleton standing in for a list row, shaped like the row it replaces so
 * the panel does not resize when the real content lands.
 */
export function SkeletonRow({ className = "" }: { className?: string }) {
  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 ${className}`}>
      <Skeleton className="h-7 w-7 shrink-0 rounded-[8px]" />
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-2.5 w-24" />
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-2.5 w-12" />
      </div>
    </div>
  );
}
