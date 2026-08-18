"use client";

import { directionGlyph, formatSignedPercent, toneClass, tonePillClass } from "@/lib/format";

/**
 * A signed, glyphed percentage.
 *
 * The arrow and the explicit sign both carry the direction, so the meaning
 * survives without colour perception. `pill` tints the background as well —
 * the platform's capsule, for the places where the number is the row's
 * headline rather than one column among many.
 */
export function ChangeBadge({
  value,
  testId,
  pill = false,
}: {
  value: number;
  testId?: string;
  pill?: boolean;
}) {
  const skin = pill
    ? `rounded-full px-2 py-0.5 text-[11px] font-semibold ${tonePillClass(value)}`
    : `text-[11px] font-semibold ${toneClass(value)}`;

  return (
    <span className={`inline-flex items-center ${skin}`} data-testid={testId}>
      <span aria-hidden="true">{directionGlyph(value)}&nbsp;</span>
      {formatSignedPercent(value)}
    </span>
  );
}
