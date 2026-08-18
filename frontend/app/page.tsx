"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { usePriceStream } from "@/lib/stream/usePriceStream";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { useChatStore } from "@/store/useChatStore";
import { Header } from "@/components/layout/Header";
import { Rail } from "@/components/layout/Rail";
import { CHART_MIN_H, PANELS } from "@/components/layout/panels";
import { WatchlistPanel } from "@/components/watchlist/WatchlistPanel";
import { PositionsTable } from "@/components/portfolio/PositionsTable";
import { TradeBar } from "@/components/trade/TradeBar";
import { ChatPanel } from "@/components/chat/ChatPanel";

// The chart bundles are the heaviest dependencies and none of them matter on
// first paint, so they load in parallel while the watchlist is already live.
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
  usePriceStream();

  const selectedTicker = useWatchlistStore((s) => s.selectedTicker);
  const refreshWatchlist = useWatchlistStore((s) => s.refresh);
  const refreshPortfolio = usePortfolioStore((s) => s.refresh);
  const refreshChat = useChatStore((s) => s.refresh);

  useEffect(() => {
    refreshWatchlist();
    refreshPortfolio();
    refreshChat();
  }, [refreshWatchlist, refreshPortfolio, refreshChat]);

  // Positions change only on a trade, but their value moves with the market,
  // so a slow poll keeps cash and cost basis honest without hammering the API.
  useEffect(() => {
    const timer = setInterval(refreshPortfolio, 15_000);
    return () => clearInterval(timer);
  }, [refreshPortfolio]);

  return (
    // On a wide screen the rail is fixed, the workspace fills what is left,
    // and each panel owns its own scroll — the shape of a real trading
    // platform. Below `lg` that inverts: the panels take their natural height
    // and the page scrolls as a whole, because a fixed viewport split four
    // ways leaves every panel too short to read.
    <div className="flex min-h-screen flex-col gap-3 p-3 lg:h-screen lg:flex-row">
      <Rail />

      <div className="flex min-w-0 flex-1 flex-col gap-3 lg:min-h-0">
        <Header />

        <main className="grid flex-1 grid-cols-1 gap-3 lg:min-h-0 lg:grid-cols-[300px_minmax(0,1fr)_320px]">
          <div className="flex min-w-0 flex-col lg:min-h-0">
            <WatchlistPanel />
          </div>

          <div className="grid min-w-0 grid-cols-1 gap-3 lg:min-h-0 lg:grid-rows-[minmax(0,1.2fr)_auto_minmax(0,0.8fr)_minmax(0,0.9fr)]">
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
      </div>
    </div>
  );
}
