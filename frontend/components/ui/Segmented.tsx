"use client";

import type { ReactNode } from "react";

/**
 * The track a segmented control sits in.
 *
 * On Apple platforms this is a sunken well holding tightly-packed segments,
 * and it is the shape that tells you the controls belong together. Exported
 * on its own because the trade ticket needs the shape without the semantics:
 * Sell and Buy are two actions, not two states of one choice, so they cannot
 * be a selection — but they read as a pair and should look like one.
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

/**
 * A single choice among a few, as one control.
 *
 * The selected segment lifts onto its own surface rather than colouring in,
 * which is how the platform marks selection here — so the control stays quiet
 * in a toolbar that already has a portfolio value competing for attention.
 */
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
  /** Names the group for assistive technology. */
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
