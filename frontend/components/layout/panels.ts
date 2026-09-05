/**
 * The panels the overview still holds, and the routes the rail navigates to.
 *
 * The ids survive the move from scroll targets to route pages: they are what
 * the onboarding tour points its spotlight at, and what each section anchors
 * itself with, so both sides still have to agree on the spelling.
 */
export const PANELS = {
  watchlist: { id: "panel-watchlist", label: "Watchlist", minH: "min-h-[320px]" },
  chart: { id: "panel-chart", label: "Markets", minH: "min-h-[280px]" },
  assistant: { id: "panel-assistant", label: "Assistant", minH: "min-h-[340px]" },
} as const;

export type PanelKey = keyof typeof PANELS;

export const CHART_MIN_H = "min-h-[220px]";

/** The rail's destinations. Trailing slashes match `trailingSlash: true`. */
export const NAV = [
  { href: "/", label: "Overview", icon: "M4 6h16M4 12h10M4 18h6" },
  { href: "/portfolio/", label: "Portfolio", icon: "M4 20V9m5 11V4m5 16v-7m5 7V11" },
  { href: "/history/", label: "History", icon: "M12 8v4l3 2M4 12a8 8 0 1 0 8-8 8 8 0 0 0-7.5 5.2M4 5v4h4" },
] as const;
