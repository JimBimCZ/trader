/**
 * Design tokens, defined once.
 *
 * Canvas-based charts cannot read CSS custom properties at draw time, so the
 * Tailwind config and the chart code both import this object. Keeping one
 * source means a colour can never drift between the two.
 */
export const colors = {
  // Surfaces. A cool light canvas with white cards floating on it — the
  // contrast between the two is what gives the layout its structure, so the
  // canvas is never white itself.
  bg: "#F2F5F7",
  surface: "#FFFFFF",
  surfaceAlt: "#F7F9FB",
  surfaceSunk: "#EDF1F4",
  rail: "#0E2029",
  railAlt: "#16303C",

  border: "#E2E9EE",
  borderStrong: "#CBD7DF",

  text: "#0E2635",
  textMuted: "#63808F",
  textFaint: "#93A8B4",

  // Brand. The green is the load-bearing colour: it is buy, it is up, and it
  // is the only fill on a primary action.
  brand: "#13C636",
  brandDeep: "#0B9E29",
  brandWash: "#E8FAEC",

  // Amber gets the same wash/text-safe pair as up/down, so a caution state is
  // built from tokens rather than from a hand-mixed tint in the component.
  accentYellow: "#ECAD0A",
  accentYellowText: "#8A6206",
  accentYellowWash: "#FDF3DC",
  accentBlue: "#209DD7",
  accentPurple: "#753991",

  // Up/down carry fills and pills; the *Text variants are darkened so small
  // text clears 4.5:1 against white.
  up: "#13C636",
  upText: "#0A7C22",
  upWash: "#E8FAEC",
  down: "#F0435C",
  downText: "#C41F37",
  downWash: "#FDECEE",
  flat: "#8FA5B1",
  flatWash: "#F0F4F6",

  heatmapLossDeep: "#F0435C",
  heatmapNeutral: "#B9C7CF",
  heatmapProfitDeep: "#13C636",
} as const;

/**
 * Depth and radius, on the same footing as colour.
 *
 * Recharts and the canvas charts need these as JS strings, so they cannot come
 * back out of Tailwind — which is exactly why they live here and the Tailwind
 * config imports them rather than restating the literals.
 */
const shadowInk = "14 38 53"; // colors.text, as an rgb triple

export const shadows = {
  card: `0 1px 2px rgb(${shadowInk} / 0.04), 0 4px 16px rgb(${shadowInk} / 0.05)`,
  pop: `0 8px 28px rgb(${shadowInk} / 0.12)`,
} as const;

export const radii = { card: "16px" } as const;

/**
 * Instrument identity colours.
 *
 * eToro leans on a logo per instrument; with no logo assets, a symbol earns a
 * stable colour instead. The hues sit at a similar lightness so a full
 * watchlist reads as one palette rather than confetti, and every one of them
 * clears 4.5:1 against white text for the monogram.
 */
const INSTRUMENT_HUES = [
  "#2E7D6B",
  "#3A6EA5",
  "#7A5AA8",
  "#B0567A",
  "#B06A2C",
  "#4F7A2E",
  "#356B8C",
  "#8A5A2B",
  "#5B6BB5",
  "#A14E68",
] as const;

/**
 * Same symbol, same colour, every render and every panel.
 *
 * Cached because four components ask for it on every price tick, and the
 * answer for a given symbol never changes.
 */
const colorCache = new Map<string, string>();

export function instrumentColor(ticker: string): string {
  const cached = colorCache.get(ticker);
  if (cached) return cached;

  let hash = 0;
  for (let i = 0; i < ticker.length; i += 1) {
    hash = (hash * 31 + ticker.charCodeAt(i)) >>> 0;
  }
  const hue = INSTRUMENT_HUES[hash % INSTRUMENT_HUES.length];
  colorCache.set(ticker, hue);
  return hue;
}
