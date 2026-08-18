"use client";

import { directionGlyph, formatSignedPercent, toneClass } from "@/lib/format";

/**
 * A signed, glyphed percentage.
 *
 * The arrow and the explicit sign both carry the direction, so the meaning
 * survives without colour perception.
 */
export function ChangeBadge({ value, testId }: { value: number; testId?: string }) {
  return (
    <span className={`tabular-nums ${toneClass(value)}`} data-testid={testId}>
      <span aria-hidden="true">{directionGlyph(value)} </span>
      {formatSignedPercent(value)}
    </span>
  );
}
