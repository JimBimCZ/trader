"use client";

import { useTheme, type ThemeMode } from "@/lib/useTheme";
import { SegmentedControl } from "./Segmented";
import { DisplayIcon, MoonIcon, SunIcon } from "./icons";

/**
 * Light, dark, or whatever the machine says.
 *
 * `system` is a first-class third choice rather than the absence of a choice,
 * because on Apple platforms it is the default and it keeps tracking the OS
 * after the fact — the store's media listener is what honours that.
 */
const OPTIONS = [
  { value: "light", label: "Light appearance", icon: <SunIcon /> },
  { value: "dark", label: "Dark appearance", icon: <MoonIcon /> },
  { value: "system", label: "Match system appearance", icon: <DisplayIcon /> },
] as const satisfies readonly { value: ThemeMode; label: string; icon: React.ReactNode }[];

export function ThemeToggle() {
  const mode = useTheme((s) => s.mode);
  const setMode = useTheme((s) => s.setMode);

  return (
    <SegmentedControl
      label="Appearance"
      value={mode}
      options={OPTIONS}
      onChange={setMode}
      className="shrink-0"
    />
  );
}
