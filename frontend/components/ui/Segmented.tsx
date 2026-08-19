"use client";

import type { ReactNode } from "react";

/**
 * The track a segmented control sits in. Exported on its own because the trade
 * ticket needs the shape without the semantics: Sell and Buy are two actions,
 * not two states of one choice, so they cannot be a selection.
 */
export function SegmentTrack({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex gap-1 rounded-control bg-surface-sunk p-1 ${className}`}>{children}</div>
  );
}

interface Option<T extends string> {
  value: T;
  label: string;
  icon?: ReactNode;
}

/** A single choice among a few, as one control. */
export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
  className = "",
}: {
  value: T;
  options: readonly Option<T>[];
  onChange: (value: T) => void;
  label: string;
  className?: string;
}) {
  return (
    <SegmentTrack className={className}>
      <div role="radiogroup" aria-label={label} className="flex gap-1">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              role="radio"
              aria-checked={selected}
              aria-label={option.label}
              title={option.label}
              onClick={() => onChange(option.value)}
              className={`flex items-center justify-center rounded-[7px] px-2.5 py-1 text-[12px]
                font-medium transition ${
                  selected
                    ? "bg-surface text-text shadow-card"
                    : "text-text-muted hover:text-text"
                }`}
            >
              {option.icon ?? option.label}
            </button>
          );
        })}
      </div>
    </SegmentTrack>
  );
}
