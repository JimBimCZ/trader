"use client";

import { useEffect } from "react";
import dynamic from "next/dynamic";
import { usePriceStream } from "@/lib/stream/usePriceStream";
import { useAppBoot } from "@/lib/useAppBoot";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { useChatStore } from "@/store/useChatStore";
import { useSessionStore } from "@/store/useSessionStore";
import { Header } from "@/components/layout/Header";
import { Rail } from "@/components/layout/Rail";
import { Footer } from "@/components/layout/Footer";
import { ThemeSync } from "@/components/layout/ThemeSync";
import { BootScreen } from "@/components/layout/BootScreen";
import { ClaimConflictDialog } from "@/components/layout/ClaimConflictDialog";
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
  usePriceStream();

  const selectedTicker = useWatchlistStore((s) => s.selectedTicker);
  const refreshWatchlist = useWatchlistStore((s) => s.refresh);
  const refreshPortfolio = usePortfolioStore((s) => s.refresh);
  const refreshChat = useChatStore((s) => s.refresh);

  const sessionVersion = useSessionStore((s) => s.sessionVersion);
  const loadSession = useSessionStore((s) => s.load);

  // Owns the first load of all four, so the boot screen can hold until they
  // have answered rather than letting the workspace assemble itself on screen.
  const booted = useAppBoot();

  // The cookie now points at a different person, so everything on screen
  // belongs to the previous one. Keyed off the counter rather than chained
  // onto sign-out, so any future path that changes identity gets this for
  // free.
  useEffect(() => {
    if (sessionVersion === 0) return;
    void refreshPortfolio();
    void refreshWatchlist();
    void refreshChat();
    void loadSession();
  }, [sessionVersion, refreshPortfolio, refreshWatchlist, refreshChat, loadSession]);

  // Positions change only on a trade, but their value moves with the market.
  useEffect(() => {
    const timer = setInterval(refreshPortfolio, 15_000);
    return () => clearInterval(timer);
  }, [refreshPortfolio]);

  return (
    // Below `lg` the fixed viewport split inverts to a page that scrolls as a
    // whole, because four panels in one viewport leaves each too short to read.
    <div
      data-booting={booted ? undefined : ""}
      className="flex min-h-screen flex-col gap-3 p-3 lg:h-screen lg:flex-row"
    >
      <ThemeSync />
      <BootScreen done={booted} />
      <ClaimConflictDialog />
      <Rail />

      <div className="flex min-w-0 flex-1 flex-col gap-3 lg:min-h-0">
        <Header />

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

        <Footer />
      </div>
    </div>
  );
}
