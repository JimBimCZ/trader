import { PANELS } from "../layout/panels";

export interface TourStep {
  /** Element id to spotlight. A step whose target is absent is skipped. */
  target: string;
  title: string;
  body: string;
}

export const TOUR_STEPS: TourStep[] = [
  {
    target: PANELS.watchlist.id,
    title: "Your watchlist",
    body: "Ten tickers, streaming live. Prices flash green on an uptick and red on a downtick. Click a row to chart it.",
  },
  {
    target: PANELS.chart.id,
    title: "The chart",
    body: "Price over time for whichever symbol you picked. It takes that instrument's colour, so the chart always matches the row you clicked.",
  },
  {
    target: "trade-ticket",
    title: "Buy and sell",
    body: "Market orders, filled instantly at the live price. You are starting with a demo portfolio and virtual cash — nothing here is real money.",
  },
  {
    target: PANELS.assistant.id,
    title: "Ask the assistant",
    body: "It can read your positions, suggest trades, and place them for you. Try \"what's my riskiest position?\"",
  },
  {
    target: "rail-portfolio",
    title: "Portfolio and history",
    body: "Your holdings, allocation and performance live on the Portfolio tab; every fill you have made is on History.",
  },
];
