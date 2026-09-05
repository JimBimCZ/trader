"use client";

import dynamic from "next/dynamic";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { CHART_MIN_H, PANELS } from "@/components/layout/panels";
import { WatchlistPanel } from "@/components/watchlist/WatchlistPanel";
import { PositionsTable } from "@/components/portfolio/PositionsTable";
import { TradeBar } from "@/components/trade/TradeBar";
import { ChatPanel } from "@/components/chat/ChatPanel";

// The chart bundles are the heaviest dependencies and none of them matter on
// first paint.
const MainChart = dynamic(
  () => import("@/components/chart/MainChart").then((m) => m.MainChart),
  { ssr: false, loading: () => <div className={`card flex-1 ${PANELS.chart.minH} lg:min-h-0`} /> },
);
const PnlChart = dynamic(
  () => import("@/components/portfolio/PnlChart").then((m) => m.PnlChart),
  { ssr: false, loading: () => <div className={`card ${CHART_MIN_H} lg:min-h-0`} /> },
);
const PortfolioHeatmap = dynamic(
  () => import("@/components/portfolio/PortfolioHeatmap").then((m) => m.PortfolioHeatmap),
  { ssr: false, loading: () => <div className={`card ${CHART_MIN_H} lg:min-h-0`} /> },
);

export default function Page() {
  const selectedTicker = useWatchlistStore((s) => s.selectedTicker);

  return (
    <main className="grid flex-1 grid-cols-1 gap-3 lg:min-h-0 lg:grid-cols-[300px_minmax(0,1fr)_320px]">
      <div className="flex min-w-0 flex-col lg:min-h-0">
        <WatchlistPanel />
      </div>

      {/* The trade ticket's row is `auto`, so it is subtracted before the
          fractions are shared out — the three chart rows get whatever is
          left of a laptop-height viewport. The heatmap/performance row
          carries two charts and needs the largest share after the main
          chart; at 0.8fr it resolved to 120px, which is less than
          Recharts' own axes occupy. */}
      <div className="grid min-w-0 grid-cols-1 gap-3 lg:min-h-0 lg:grid-rows-[minmax(0,1.15fr)_auto_minmax(0,1.05fr)_minmax(0,0.8fr)]">
        <MainChart ticker={selectedTicker} />
        <TradeBar />
        <div className="grid min-w-0 grid-cols-1 gap-3 lg:min-h-0 xl:grid-cols-2">
          <PortfolioHeatmap />
          <PnlChart />
        </div>
        <PositionsTable />
      </div>

      <div className="flex min-w-0 flex-col lg:min-h-0">
        <ChatPanel />
      </div>
    </main>
  );
}
