import type { Config } from "tailwindcss";
import { radii, tailwindColors } from "./lib/theme";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  // The appearance is an attribute rather than a class, because the pre-paint
  // script writes it as `data-theme` and a `dark:` variant has to agree with
  // whatever that script set before React exists.
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      // Derived from the palette's own token list rather than restated here,
      // so a new colour is one edit in `lib/theme.ts` and nothing else.
      colors: tailwindColors(),
      fontFamily: {
        // Resolves to the real SF Pro on every Mac and iPhone, Segoe UI
        // Variable on Windows, and the platform default elsewhere. Nothing is
        // downloaded, so the export carries no font files and the build needs
        // no network to produce them.
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Text",
          "SF Pro Display",
          "Segoe UI Variable Text",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      borderRadius: radii,
      // Both appearances define these, so the shadow follows the theme without
      // a `dark:` variant at every call site.
      boxShadow: { card: "var(--shadow-card)", pop: "var(--shadow-pop)" },
      // Apple's hairline: one device pixel, not one CSS pixel.
      borderWidth: { hairline: "0.5px" },
    },
  },
  plugins: [],
} satisfies Config;
