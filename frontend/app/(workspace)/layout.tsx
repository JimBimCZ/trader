"use client";

import { useEffect } from "react";
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
import { TradeReceiptDialog } from "@/components/trade/TradeReceiptDialog";

/**
 * The workspace shell, shared by every route in this group.
 *
 * It is a layout rather than something each page renders so that navigating
 * between Overview, Portfolio and History does not remount it: one
 * EventSource stays open across the whole workspace, and the lazily-imported
 * chart bundles stay warm. A per-page shell would reconnect the stream and
 * re-download a chart bundle on every tab switch, which is the objection that
 * usually makes real routes a bad trade — this is what answers it.
 *
 * `/privacy/` sits outside the group deliberately: a reading page has no
 * business holding a price stream open.
 */
export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  usePriceStream();

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
    void refreshPortfolio().catch(() => {});
    void refreshWatchlist().catch(() => {});
    void refreshChat().catch(() => {});
    void loadSession().catch(() => {});
  }, [sessionVersion, refreshPortfolio, refreshWatchlist, refreshChat, loadSession]);

  // Positions change only on a trade, but their value moves with the market.
  useEffect(() => {
    // A failed revaluation is already recorded on the store; the next tick
    // retries it, so there is nothing here to handle.
    const timer = setInterval(() => void refreshPortfolio().catch(() => {}), 15_000);
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
      <TradeReceiptDialog />
      <Rail />

      <div className="flex min-w-0 flex-1 flex-col gap-3 lg:min-h-0">
        <Header />
        {children}
        <Footer />
      </div>
    </div>
  );
}
