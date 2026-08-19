/**
 * The workspace panels the rail can navigate to. The rail resolves its targets
 * with `getElementById`, so the ids have to agree — a pairing nothing would
 * catch at build time if each side spelled it out separately.
 */
export const PANELS = {
  watchlist: { id: "panel-watchlist", label: "Watchlist", minH: "min-h-[320px]" },
  chart: { id: "panel-chart", label: "Markets", minH: "min-h-[280px]" },
  portfolio: { id: "panel-portfolio", label: "Portfolio", minH: "min-h-[220px]" },
  assistant: { id: "panel-assistant", label: "Assistant", minH: "min-h-[340px]" },
} as const;

export type PanelKey = keyof typeof PANELS;

export const CHART_MIN_H = "min-h-[220px]";
