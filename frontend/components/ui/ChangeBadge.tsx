"use client";

import { directionGlyph, formatSignedPercent, toneClass, tonePillClass } from "@/lib/format";

/**
 * A signed, glyphed percentage — the arrow and sign carry the direction, so
 * the meaning survives without colour perception.
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
