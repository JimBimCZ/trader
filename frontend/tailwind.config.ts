import type { Config } from "tailwindcss";
import { radii, tailwindColors } from "./lib/theme";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  // `data-theme` rather than a class, because the pre-paint script writes it
  // as an attribute before React exists.
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: tailwindColors(),
      fontFamily: {
        // Resolves to the real SF Pro on Apple platforms and Segoe UI Variable
        // on Windows. Nothing is downloaded.
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
      boxShadow: { card: "var(--shadow-card)", pop: "var(--shadow-pop)" },
      // Apple's hairline: one device pixel, not one CSS pixel.
      borderWidth: { hairline: "0.5px" },
    },
  },
  plugins: [],
} satisfies Config;
