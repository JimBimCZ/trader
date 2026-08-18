"use client";

import { directionGlyph, formatSignedCurrency, toneClass } from "@/lib/format";

/**
 * A signed, glyphed currency amount — `ChangeBadge`'s sibling for money.
 *
 * The arrow and the explicit sign both carry the direction, so a P&L reads
 * correctly without colour perception. Pairing the tone with the glyph in one
 * place is what stops a coloured figure shipping without its arrow.
 */
export function SignedValue({
  value,
  className = "",
  testId,
}: {
  value: number;
  className?: string;
  testId?: string;
}) {
  return (
    <span className={`${toneClass(value)} ${className}`} data-testid={testId}>
      <span aria-hidden="true">{directionGlyph(value)}&nbsp;</span>
      {formatSignedCurrency(value)}
    </span>
  );
}
