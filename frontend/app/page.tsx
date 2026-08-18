"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { usePriceStream } from "@/lib/stream/usePriceStream";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { useChatStore } from "@/store/useChatStore";
import { Header } from "@/components/layout/Header";
import { WatchlistPanel } from "@/components/watchlist/WatchlistPanel";
import { PositionsTable } from "@/components/portfolio/PositionsTable";
import { TradeBar } from "@/components/trade/TradeBar";
import { ChatPanel } from "@/components/chat/ChatPanel";

// The chart bundles are the heaviest dependencies and none of them matter on
// first paint, so they load in parallel while the watchlist is already live.
const MainChart = dynamic(
  () => import("@/components/chart/MainChart").then((m) => m.MainChart),
  { ssr: false, loading: () => <div className="panel min-h-0 flex-1" /> },
);
const PnlChart = dynamic(
  () => import("@/components/portfolio/PnlChart").then((m) => m.PnlChart),
  { ssr: false, loading: () => <div className="panel min-h-0" /> },
);
const PortfolioHeatmap = dynamic(
  () => import("@/components/portfolio/PortfolioHeatmap").then((m) => m.PortfolioHeatmap),
  { ssr: false, loading: () => <div className="panel min-h-0" /> },
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
    <div className="flex h-screen flex-col gap-2 p-2">
      <Header />

      <main className="grid min-h-0 flex-1 grid-cols-1 gap-2 lg:grid-cols-[320px_minmax(0,1fr)_340px]">
        <div className="flex min-h-0 flex-col gap-2">
          <WatchlistPanel />
        </div>

        <div className="grid min-h-0 grid-rows-[minmax(0,1.15fr)_minmax(0,0.85fr)_auto_minmax(0,0.9fr)] gap-2">
          <MainChart ticker={selectedTicker} />
          <div className="grid min-h-0 grid-cols-1 gap-2 xl:grid-cols-2">
            <PortfolioHeatmap />
            <PnlChart />
          </div>
          <TradeBar />
          <PositionsTable />
        </div>

        <div className="flex min-h-0 flex-col gap-2">
          <ChatPanel />
        </div>
      </main>
    </div>
  );
}
