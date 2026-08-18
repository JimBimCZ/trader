/** Display formatters. Every number the user sees goes through one of these. */

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

/**
 * Pick by sign, once.
 *
 * Every direction-dependent value in the app — glyph, sign, text colour, pill
 * skin — is the same three-way choice. Writing it once means the flat case
 * cannot be forgotten at one call site and honoured at another.
 */
const bySign = <T,>(value: number, up: T, down: T, flat: T): T =>
  value > 0 ? up : value < 0 ? down : flat;

const signChar = (value: number): string => bySign(value, "+", "-", "");

/** Signed currency, e.g. "+$12.40". Sign is always explicit. */
export function formatSignedCurrency(value: number): string {
  return `${signChar(value)}${currency.format(Math.abs(value))}`;
}

/** Signed percentage, e.g. "+0.65%". */
export function formatSignedPercent(value: number): string {
  return `${signChar(value)}${Math.abs(value).toFixed(2)}%`;
}

/** Quantities drop trailing zeros: 10, 0.5, 1.234568. */
export function formatQuantity(value: number): string {
  return Number(value.toFixed(6)).toString();
}

/**
 * The glyph paired with every coloured number.
 *
 * Colour alone is not an accessible encoding, so a direction always carries a
 * shape as well.
 */
export const directionGlyph = (value: number): string => bySign(value, "▲", "▼", "–");

export const toneClass = (value: number): string =>
  bySign(value, "text-up-text", "text-down-text", "text-flat");

/** The tinted pill a change percentage sits in. Tone plus its own wash. */
export const tonePillClass = (value: number): string =>
  bySign(value, "bg-up-wash text-up-text", "bg-down-wash text-down-text", "bg-flat-wash text-flat");

/**
 * Chart clocks, in the viewer's local time.
 *
 * Both charts key their series by UTC, and an axis left on its default would
 * put a different clock on one chart than on the one beside it. Cached `Intl`
 * instances also keep the 2Hz chart from allocating a formatter per tick mark.
 */
const clock = new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit" });
const clockSeconds = new Intl.DateTimeFormat([], {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

/** Epoch seconds to a local `hh:mm:ss`. */
export const formatClockSeconds = (epochSeconds: number): string =>
  clockSeconds.format(epochSeconds * 1000);

/** An ISO timestamp to a local `hh:mm`. */
export const formatIsoClock = (iso: string): string => clock.format(new Date(iso));
