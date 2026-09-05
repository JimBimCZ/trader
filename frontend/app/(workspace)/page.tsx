"use client";

import dynamic from "next/dynamic";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { PANELS } from "@/components/layout/panels";
import { WatchlistPanel } from "@/components/watchlist/WatchlistPanel";
import { TradeBar } from "@/components/trade/TradeBar";
import { ChatPanel } from "@/components/chat/ChatPanel";

// The chart bundles are the heaviest dependencies and none of them matter on
// first paint.
const MainChart = dynamic(
  () => import("@/components/chart/MainChart").then((m) => m.MainChart),
  { ssr: false, loading: () => <div className={`card flex-1 ${PANELS.chart.minH} lg:min-h-0`} /> },
);

export default function Page() {
  const selectedTicker = useWatchlistStore((s) => s.selectedTicker);

  return (
    <main className="grid flex-1 grid-cols-1 gap-3 lg:min-h-0 lg:grid-cols-[300px_minmax(0,1fr)_320px]">
      <div className="flex min-w-0 flex-col lg:min-h-0">
        <WatchlistPanel />
      </div>

      {/* The ticket's row is `auto`, so it is subtracted before the
          fraction is shared out and the chart takes everything else --
          which is the whole point of moving the portfolio panels to
          their own route. */}
      <div className="grid min-w-0 grid-cols-1 gap-3 lg:min-h-0 lg:grid-rows-[minmax(0,1fr)_auto]">
        <MainChart ticker={selectedTicker} />
        <TradeBar />
      </div>

      <div className="flex min-w-0 flex-col lg:min-h-0">
        <ChatPanel />
      </div>
    </main>
  );
}
