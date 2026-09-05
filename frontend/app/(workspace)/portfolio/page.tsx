"use client";

import dynamic from "next/dynamic";
import { PositionsTable } from "@/components/portfolio/PositionsTable";
import { CHART_MIN_H } from "@/components/layout/panels";

const PnlChart = dynamic(
  () => import("@/components/portfolio/PnlChart").then((m) => m.PnlChart),
  { ssr: false, loading: () => <div className={`card ${CHART_MIN_H} lg:min-h-0`} /> },
);
const PortfolioHeatmap = dynamic(
  () => import("@/components/portfolio/PortfolioHeatmap").then((m) => m.PortfolioHeatmap),
  { ssr: false, loading: () => <div className={`card ${CHART_MIN_H} lg:min-h-0`} /> },
);

/**
 * The portfolio, at the size it needs to be read.
 *
 * On the overview these three shared one column with the main chart and the
 * trade ticket, which left the heatmap and the performance chart resolving to
 * less than Recharts' own axes occupy. Here the charts get half the width
 * each and the table gets all of it.
 */
export default function PortfolioPage() {
  return (
    <main className="grid flex-1 grid-cols-1 gap-3 lg:min-h-0 lg:grid-rows-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <div className="grid min-w-0 grid-cols-1 gap-3 lg:min-h-0 lg:grid-cols-2">
        <PortfolioHeatmap />
        <PnlChart />
      </div>
      <PositionsTable />
    </main>
  );
}
