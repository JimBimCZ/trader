"use client";

import { create } from "zustand";
import { palettes, type Appearance, type Palette } from "./theme";

/** `system` defers to the OS, and keeps deferring. */
export type ThemeMode = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "trader-theme";

interface ThemeState {
  mode: ThemeMode;
  appearance: Appearance;
  palette: Palette;
  setMode: (mode: ThemeMode) => void;
  /**
   * Adopts what the pre-paint script already resolved, and starts following
   * the system setting. Called once, on mount; returns its own teardown.
   */
  hydrate: () => () => void;
}

const MEDIA = "(prefers-color-scheme: dark)";

function systemAppearance(): Appearance {
  if (typeof window === "undefined") return "light";
  return window.matchMedia(MEDIA).matches ? "dark" : "light";
}

export function resolve(mode: ThemeMode): Appearance {
  return mode === "system" ? systemAppearance() : mode;
}

function apply(appearance: Appearance, mode: ThemeMode) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  root.dataset.theme = appearance;
  root.dataset.themeMode = mode;
}

/**
 * The current appearance, for the consumers that draw outside CSS:
 * lightweight-charts into a canvas, Recharts into SVG attributes, and the
 * instrument chips, whose colour is per-symbol and so cannot be a variable.
 *
 * It initialises to `light` unconditionally rather than reading the DOM,
 * because the pages are prerendered and a first render that disagreed with the
 * exported HTML would be a hydration mismatch. `hydrate` picks up the truth
 * immediately after mount, from the attribute the pre-paint script set.
 */
export const useTheme = create<ThemeState>((set, get) => ({
  mode: "system",
  appearance: "light",
  palette: palettes.light,

  setMode: (mode) => {
    const appearance = resolve(mode);
    apply(appearance, mode);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, mode);
    } catch {
      // Private browsing denies storage; the choice lasts one session.
    }
    set({ mode, appearance, palette: palettes[appearance] });
  },

  hydrate: () => {
    const stored = (() => {
      try {
        return window.localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode | null;
      } catch {
        return null;
      }
    })();
    const mode: ThemeMode = stored ?? "system";
    const appearance = resolve(mode);
    apply(appearance, mode);
    if (get().appearance !== appearance || get().mode !== mode) {
      set({ mode, appearance, palette: palettes[appearance] });
    }

    // Following the system means following it after mount too, not just at it.
    const media = window.matchMedia(MEDIA);
    const onChange = () => {
      if (get().mode !== "system") return;
      const next = systemAppearance();
      apply(next, "system");
      set({ appearance: next, palette: palettes[next] });
    };
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  },
}));

export const usePalette = (): Palette => useTheme((s) => s.palette);
