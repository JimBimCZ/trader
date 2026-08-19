"use client";

import { useTheme, type ThemeMode } from "@/lib/useTheme";
import { SegmentedControl } from "./Segmented";
import { DisplayIcon, MoonIcon, SunIcon } from "./icons";

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
