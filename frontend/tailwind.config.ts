import type { Config } from "tailwindcss";
import { colors, radii, shadows } from "./lib/theme";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: colors.bg,
        surface: colors.surface,
        "surface-alt": colors.surfaceAlt,
        "surface-sunk": colors.surfaceSunk,
        rail: colors.rail,
        "rail-alt": colors.railAlt,
        border: colors.border,
        "border-strong": colors.borderStrong,
        text: colors.text,
        "text-muted": colors.textMuted,
        "text-faint": colors.textFaint,
        brand: colors.brand,
        "brand-deep": colors.brandDeep,
        "brand-wash": colors.brandWash,
        yellow: colors.accentYellow,
        "yellow-text": colors.accentYellowText,
        "yellow-wash": colors.accentYellowWash,
        blue: colors.accentBlue,
        purple: colors.accentPurple,
        up: colors.up,
        "up-text": colors.upText,
        "up-wash": colors.upWash,
        down: colors.down,
        "down-text": colors.downText,
        "down-wash": colors.downWash,
        flat: colors.flat,
        "flat-wash": colors.flatWash,
      },
      fontFamily: {
        // Figtree carries the personality; Inter carries the numbers, because
        // its tabular figures are the reason prices do not jitter.
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        sans: ["var(--font-body)", "system-ui", "sans-serif"],
      },
      borderRadius: radii,
      boxShadow: shadows,
    },
  },
  plugins: [],
} satisfies Config;
