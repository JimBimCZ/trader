"use client";

import { TradeHistoryTable } from "@/components/portfolio/TradeHistoryTable";

/** Every fill, newest first, and what each sale made. */
export default function HistoryPage() {
  return (
    <main className="flex flex-1 flex-col lg:min-h-0">
      <TradeHistoryTable />
    </main>
  );
}
