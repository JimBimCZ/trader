/**
 * Design tokens, defined once — now in two appearances.
 *
 * Two consumers need these values and they need them in different forms:
 * Tailwind resolves classes at build time, while the canvas and SVG charts
 * need a concrete colour string at draw time. A single static object could
 * serve both only while there was one appearance. With light and dark it
 * cannot, so the one source forks into two outputs instead of two sources:
 *
 *   palettes ──┬─→ themeStyleSheet()  →  :root custom properties  →  Tailwind
 *              └─→ useTheme().palette →  lightweight-charts, Recharts, SVG
 *
 * Every colour is emitted as an "R G B" channel triple rather than a hex
 * string, because Tailwind's alpha modifiers (`bg-blue/15`) compose onto
 * `rgb(var(--c-blue) / <alpha-value>)` and cannot compose onto a hex.
 *
 * The palette is Apple's system colour set, with one deliberate departure.
 * A system colour is chosen to look right, not to carry text: white on
 * systemGreen is 2.2:1 and systemGreen on white is 1.9:1, so a token that has
 * to do both jobs cannot do either well. Each direction colour therefore
 * splits three ways —
 *
 *   up       the vivid system colour, for anything that is not text:
 *            chart strokes, the flash tint, a status dot, a heatmap cell
 *   upFill   darkened until a white label on it clears 4.5:1, for buttons
 *   upText   darkened until it clears 4.5:1 *as* small text on a surface
 *
 * — and `__tests__/lib/theme.test.ts` holds every one of those pairings to
 * the line, in both appearances, so this cannot quietly drift.
 */

export type ColorToken = keyof typeof LIGHT_COLORS;

const LIGHT_COLORS = {
  // Surfaces. systemGroupedBackground under white cards: on Apple platforms
  // the canvas is the grey and the content is the white, never the reverse.
  bg: "#F2F2F7",
  surface: "#FFFFFF",
  surfaceAlt: "#F7F7FA",
  surfaceSunk: "#EBEBF0",
  // The base tint of the translucent chrome. It is never painted at full
  // opacity — the sidebar and toolbar draw it through a backdrop blur.
  material: "#F6F6F8",

  // Separators. Apple draws structure with hairlines, not with shadow.
  border: "#D8D8DC",
  borderStrong: "#C6C6C8",

  // Label hierarchy. Apple's own secondaryLabel resolves to about 3.0:1,
  // which this app's accessibility floor does not allow, so the muted tone is
  // darkened until it clears 4.5:1 on both the card and the canvas.
  text: "#000000",
  textMuted: "#5B5B60",
  textFaint: "#8E8E93",

  // systemBlue: the interaction colour, and only that. Nothing directional is
  // ever blue, and nothing interactive is ever green.
  blue: "#007AFF",
  blueFill: "#0071EB",
  blueText: "#0040DD",
  blueWash: "#E5F1FF",

  // Direction. systemGreen and systemRed carry the direction; the *Text and
  // *Fill variants carry the text.
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

  // systemOrange, carrying the same fill/text/wash triplet, so the connecting
  // state is built from tokens rather than a tint mixed in the component.
  yellow: "#FF9500",
  yellowText: "#A85700",
  yellowWash: "#FFF1E0",

  heatmapProfitDeep: "#34C759",
  heatmapLossDeep: "#FF3B30",
  heatmapNeutral: "#C7C7CC",

  /** The monogram colour inside an instrument chip. */
  instrumentInk: "#FFFFFF",
} as const;

const DARK_COLORS: Record<ColorToken, string> = {
  // True black, not charcoal: it is what Apple ships, and it is what makes
  // the elevated card read as a separate plane without a shadow to say so.
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

  // The dark chips are bright enough that near-black is the legible monogram.
  instrumentInk: "#0B0B0C",
};

/**
 * Instrument identity colours.
 *
 * With no logo assets, a symbol earns a stable colour instead. The hues sit
 * at a similar lightness so a full watchlist reads as one palette rather than
 * confetti, and each set is chosen against its own monogram ink: the light
 * hues are deep enough for white text, the dark ones bright enough for black.
 * None of them is systemGreen, systemRed, or systemBlue — those three are
 * spoken for.
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
  /** Full CSS shadow strings — dark leans on hairlines, so its are lighter. */
  shadows: { card: string; pop: string };
  /**
   * How strongly a price tick tints its cell.
   *
   * Not a colour but a property of one, and it cannot be a single number: the
   * same alpha that is a shimmer on white is a filled badge on black. At a
   * 500ms tick almost every row is mid-animation at any moment, so getting
   * this wrong on one appearance makes the whole column strobe.
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

/**
 * The colour map Tailwind is configured with.
 *
 * Derived from the token list rather than restated, so adding a colour to the
 * palette is one edit rather than three that can disagree.
 */
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
 * Both appearances, as one stylesheet.
 *
 * Emitted into the document head at build time rather than hand-written in
 * `globals.css`, because a CSS file cannot import this module and a hand-kept
 * copy of thirty colours is a copy that drifts. `data-theme` is stamped on the
 * root element before first paint, so no rule here is ever applied late.
 */
export function themeStyleSheet(): string {
  return [block(":root", palettes.light), block(':root[data-theme="dark"]', palettes.dark)].join("");
}

/**
 * Same symbol, same colour, every render and every panel.
 *
 * Cached because four components ask for it on every price tick, and the
 * answer for a given symbol and appearance never changes.
 */
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
 * Corner radii.
 *
 * Larger than the platform-neutral defaults because Apple's corners are
 * continuous: an ordinary circular corner at the same radius reads tighter
 * than the squircle it stands in for. Where the browser supports
 * `corner-shape`, `globals.css` upgrades these to the real curve.
 */
export const radii = {
  control: "10px",
  card: "14px",
  panel: "20px",
} as const;

/** Apple's standard ease. Everything that moves in this app uses it. */
export const EASE = "cubic-bezier(0.32, 0.72, 0, 1)";
