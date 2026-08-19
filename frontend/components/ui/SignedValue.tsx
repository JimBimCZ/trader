"use client";

import { directionGlyph, formatSignedCurrency, toneClass } from "@/lib/format";

/** `ChangeBadge`'s sibling for money: signed, glyphed, toned. */
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
