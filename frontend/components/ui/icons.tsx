"use client";

/** The dismiss mark, shared by the watchlist row and the assistant panel. */
export function CloseIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
    </svg>
  );
}

/**
 * The appearance glyphs.
 *
 * Drawn from one stroke width and one cap style so the three read as a set
 * inside the segmented control, the way SF Symbols do.
 */
const stroke = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.8,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export function SunIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="4.2" {...stroke} />
      <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.2 5.2l1.6 1.6M17.2 17.2l1.6 1.6M18.8 5.2l-1.6 1.6M6.8 17.2l-1.6 1.6" {...stroke} />
    </svg>
  );
}

export function MoonIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M20 13.6A8.2 8.2 0 1 1 10.4 4a6.6 6.6 0 0 0 9.6 9.6z" {...stroke} />
    </svg>
  );
}

/** System appearance: a display, because the choice belongs to the machine. */
export function DisplayIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect x="3" y="4.5" width="18" height="12" rx="2.2" {...stroke} />
      <path d="M9 20h6M12 16.5V20" {...stroke} />
    </svg>
  );
}
