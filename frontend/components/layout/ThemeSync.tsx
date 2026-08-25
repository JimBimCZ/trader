"use client";

import { useEffect } from "react";
import { useTheme } from "@/lib/useTheme";

/**
 * Keeps a page following the OS appearance for as long as it is open.
 *
 * The pre-paint script in the root layout resolves the appearance before
 * anything is drawn, but it runs exactly once. `system` is specified to keep
 * deferring to the OS while the page is open (PLAN.md §2), and the listener
 * that does that lives in the theme store — so a page that never mounts the
 * store is correct at load and then frozen.
 */
export function ThemeSync() {
  const hydrate = useTheme((s) => s.hydrate);
  useEffect(hydrate, [hydrate]);
  return null;
}
