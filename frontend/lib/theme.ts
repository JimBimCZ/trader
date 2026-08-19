/**
 * Design tokens, defined once and emitted twice: as CSS custom properties for
 * Tailwind, and as a plain object for the canvas and SVG charts, which need a
 * concrete colour at draw time and cannot read a custom property.
 *
 * Colours are emitted as "R G B" channel triples, not hex, because Tailwind's
 * alpha modifiers compose onto `rgb(var(--c-blue) / <alpha-value>)`.
 *
 * Each direction colour splits three ways: the vivid system colour for
 * anything that is not text, `*Fill` darkened until white text on it clears
 * 4.5:1, and `*Text` darkened until it clears 4.5:1 on a surface.
 * `__tests__/lib/theme.test.ts` holds every pairing to that floor.
 */

export type ColorToken = keyof typeof LIGHT_COLORS;

const LIGHT_COLORS = {
  bg: "#F2F2F7",
  surface: "#FFFFFF",
  surfaceAlt: "#F7F7FA",
  surfaceSunk: "#EBEBF0",
  // Never painted at full opacity — the sidebar and toolbar draw it through a
  // backdrop blur.
  material: "#F6F6F8",

  border: "#D8D8DC",
  borderStrong: "#C6C6C8",

  text: "#000000",
  // Apple's own secondaryLabel resolves to about 3.0:1, so the muted tone is
  // darkened until it clears 4.5:1 on both the card and the canvas.
  textMuted: "#5B5B60",
  textFaint: "#8E8E93",

  blue: "#007AFF",
  blueFill: "#0071EB",
  blueText: "#0040DD",
  blueWash: "#E5F1FF",

  up: "#34C759",
  upFill: "#1F7F33",
  upText: "#1E7A32",
  upWash: "#E4F8EA",
  down: "#FF3B30",
  downFill: "#E02A20",
  downText: "#D70015",
  downWash: "#FFE9E7",
  flat: "#66666A",
  flatWash: "#EBEBF0",

  yellow: "#FF9500",
  yellowText: "#A85700",
  yellowWash: "#FFF1E0",

  heatmapProfitDeep: "#34C759",
  heatmapLossDeep: "#FF3B30",
  heatmapNeutral: "#C7C7CC",

  instrumentInk: "#FFFFFF",
} as const;

const DARK_COLORS: Record<ColorToken, string> = {
  bg: "#000000",
  surface: "#1C1C1E",
  surfaceAlt: "#242426",
  surfaceSunk: "#2C2C2E",
  material: "#1C1C1E",

  border: "#38383A",
  borderStrong: "#48484A",

  text: "#FFFFFF",
  textMuted: "#A1A1A6",
  textFaint: "#8E8E93",

  blue: "#0A84FF",
  blueFill: "#0A70DE",
  blueText: "#4DA3FF",
  blueWash: "#14304A",

  up: "#30D158",
  upFill: "#22883A",
  upText: "#30D158",
  upWash: "#14301C",
  down: "#FF453A",
  downFill: "#DE2A20",
  downText: "#FF453A",
  downWash: "#3A1512",
  flat: "#98989D",
  flatWash: "#2C2C2E",

  yellow: "#FF9F0A",
  yellowText: "#FFB340",
  yellowWash: "#3A2510",

  heatmapProfitDeep: "#30D158",
  heatmapLossDeep: "#FF453A",
  heatmapNeutral: "#48484A",

  instrumentInk: "#0B0B0C",
};

/**
 * Instrument identity colours, standing in for logo assets. The light hues are
 * deep enough to carry white monogram ink, the dark ones bright enough to
 * carry near-black. None is systemBlue, systemGreen, or systemRed.
 */
const LIGHT_INSTRUMENTS = [
  "#0A6EA8",
  "#5856D6",
  "#8944AB",
  "#B03A5B",
  "#C05621",
  "#2E7D6B",
  "#35688A",
  "#8A5A2B",
  "#5B6BB5",
  "#A14E68",
] as const;

const DARK_INSTRUMENTS = [
  "#4FB3E8",
  "#9B99FF",
  "#D08BEE",
  "#FF8FA8",
  "#FFAB6B",
  "#5FD2B8",
  "#8FBEDE",
  "#D9A56B",
  "#A5B0F0",
  "#EE93AC",
] as const;

export type Appearance = "light" | "dark";

export interface Palette {
  appearance: Appearance;
  colors: Record<ColorToken, string>;
  shadows: { card: string; pop: string };
  /**
   * How strongly a price tick tints its cell. The alpha that is a shimmer on
   * white is a filled badge on black, so it cannot be one number.
   */
  flashAlpha: number;
  instruments: readonly string[];
}

export const palettes: Record<Appearance, Palette> = {
  light: {
    appearance: "light",
    colors: LIGHT_COLORS,
    shadows: {
      card: "0 1px 1px rgb(0 0 0 / 0.04), 0 6px 20px rgb(0 0 0 / 0.06)",
      pop: "0 10px 40px rgb(0 0 0 / 0.16)",
    },
    flashAlpha: 0.17,
    instruments: LIGHT_INSTRUMENTS,
  },
  dark: {
    appearance: "dark",
    colors: DARK_COLORS,
    shadows: {
      card: "0 1px 1px rgb(0 0 0 / 0.4), 0 8px 24px rgb(0 0 0 / 0.5)",
      pop: "0 12px 44px rgb(0 0 0 / 0.7)",
    },
    flashAlpha: 0.13,
    instruments: DARK_INSTRUMENTS,
  },
};

/** `surfaceAlt` → `surface-alt`, the spelling Tailwind and CSS both use. */
const kebab = (token: string): string => token.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

/** `#34C759` → `52 199 89`, so an alpha modifier can be composed onto it. */
function channels(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

const TOKENS = Object.keys(LIGHT_COLORS) as ColorToken[];

/** The colour map Tailwind is configured with. */
export function tailwindColors(): Record<string, string> {
  return Object.fromEntries(
    TOKENS.map((token) => [kebab(token), `rgb(var(--c-${kebab(token)}) / <alpha-value>)`]),
  );
}

function block(selector: string, palette: Palette): string {
  const vars = TOKENS.map((t) => `--c-${kebab(t)}:${channels(palette.colors[t])}`).join(";");
  return (
    `${selector}{color-scheme:${palette.appearance};${vars};` +
    `--shadow-card:${palette.shadows.card};--shadow-pop:${palette.shadows.pop};` +
    `--flash-alpha:${palette.flashAlpha}}`
  );
}

/**
 * Both appearances, as one stylesheet injected into the document head. A CSS
 * file cannot import this module, and a hand-kept copy of thirty colours
 * drifts.
 */
export function themeStyleSheet(): string {
  return [block(":root", palettes.light), block(':root[data-theme="dark"]', palettes.dark)].join("");
}

// Four components ask for an instrument colour on every price tick, and the
// answer for a given symbol and appearance never changes.
const colorCache = new Map<string, string>();

export function instrumentColor(ticker: string, appearance: Appearance = "light"): string {
  const key = `${appearance}:${ticker}`;
  const cached = colorCache.get(key);
  if (cached) return cached;

  let hash = 0;
  for (let i = 0; i < ticker.length; i += 1) {
    hash = (hash * 31 + ticker.charCodeAt(i)) >>> 0;
  }
  const hues = palettes[appearance].instruments;
  const hue = hues[hash % hues.length];
  colorCache.set(key, hue);
  return hue;
}

/**
 * Larger than platform-neutral defaults because Apple's corners are
 * continuous; `globals.css` upgrades these to `corner-shape` where supported.
 */
export const radii = {
  control: "10px",
  card: "14px",
  panel: "20px",
} as const;

/** Apple's standard ease. Everything that moves in this app uses it. */
export const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";
