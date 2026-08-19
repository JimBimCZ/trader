const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const compactCurrency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

export const formatPrice = (value: number): string => currency.format(value);

export const formatCompact = (value: number): string => compactCurrency.format(value);

/** Every direction-dependent value in the app is the same three-way choice. */
const bySign = <T,>(value: number, up: T, down: T, flat: T): T =>
  value > 0 ? up : value < 0 ? down : flat;

const signChar = (value: number): string => bySign(value, "+", "-", "");

export function formatSignedCurrency(value: number): string {
  return `${signChar(value)}${currency.format(Math.abs(value))}`;
}

export function formatSignedPercent(value: number): string {
  return `${signChar(value)}${Math.abs(value).toFixed(2)}%`;
}

export function formatQuantity(value: number): string {
  return Number(value.toFixed(6)).toString();
}

/** Colour alone is not an accessible encoding, so direction carries a shape. */
export const directionGlyph = (value: number): string => bySign(value, "▲", "▼", "–");

export const toneClass = (value: number): string =>
  bySign(value, "text-up-text", "text-down-text", "text-flat");

export const tonePillClass = (value: number): string =>
  bySign(value, "bg-up-wash text-up-text", "bg-down-wash text-down-text", "bg-flat-wash text-flat");

// Both charts key their series by UTC, and an axis left on its default would
// put a different clock on one chart than on the one beside it.
const clock = new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit" });
const clockSeconds = new Intl.DateTimeFormat([], {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export const formatClockSeconds = (epochSeconds: number): string =>
  clockSeconds.format(epochSeconds * 1000);

export const formatIsoClock = (iso: string): string => clock.format(new Date(iso));
