import type { Config } from "tailwindcss";
import { colors } from "./lib/theme";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: colors.bg,
        "bg-alt": colors.bgAlt,
        "bg-raised": colors.bgRaised,
        border: colors.border,
        "border-bright": colors.borderBright,
        text: colors.text,
        "text-muted": colors.textMuted,
        yellow: colors.accentYellow,
        blue: colors.accentBlue,
        purple: colors.accentPurple,
        up: colors.up,
        "up-text": colors.upText,
        down: colors.down,
        "down-text": colors.downText,
        flat: colors.flat,
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
} satisfies Config;
