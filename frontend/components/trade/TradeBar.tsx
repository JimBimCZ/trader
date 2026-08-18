"use client";

import { useState } from "react";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { Button } from "../ui/Button";

export function TradeBar() {
  const selected = useWatchlistStore((s) => s.selectedTicker);
  const trade = usePortfolioStore((s) => s.trade);
  const pending = usePortfolioStore((s) => s.tradePending);
  const error = usePortfolioStore((s) => s.tradeError);
  const clearError = usePortfolioStore((s) => s.clearTradeError);

  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");

  const effectiveTicker = (ticker || selected || "").toUpperCase();
  const parsedQuantity = Number(quantity);
  const valid = effectiveTicker.length > 0 && Number.isFinite(parsedQuantity) && parsedQuantity > 0;

  async function submit(side: "buy" | "sell") {
    if (!valid || pending) return;
    if (await trade(effectiveTicker, side, parsedQuantity)) {
      setQuantity("");
    }
  }

  return (
    <section className="panel p-2" aria-label="Trade">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={ticker}
          onChange={(event) => {
            setTicker(event.target.value.toUpperCase());
            if (error) clearError();
          }}
          placeholder={selected ?? "TICKER"}
          maxLength={5}
          aria-label="Ticker to trade"
          data-testid="trade-ticker"
          className="w-24 rounded border border-border bg-bg px-2 py-1.5 text-xs uppercase tracking-wider text-text placeholder:text-flat focus:border-blue focus:outline-none"
        />
        <input
          value={quantity}
          onChange={(event) => {
            setQuantity(event.target.value);
            if (error) clearError();
          }}
          type="number"
          min="0"
          step="any"
          placeholder="QTY"
          aria-label="Quantity to trade"
          data-testid="trade-quantity"
          className="w-28 rounded border border-border bg-bg px-2 py-1.5 text-xs tabular-nums text-text placeholder:text-flat focus:border-blue focus:outline-none"
        />
        {/* Disabled while a request is in flight, which is all the
            double-submit protection a fake-money demo warrants. */}
        <Button variant="buy" disabled={!valid || pending} onClick={() => submit("buy")} data-testid="buy-button">
          Buy
        </Button>
        <Button variant="sell" disabled={!valid || pending} onClick={() => submit("sell")} data-testid="sell-button">
          Sell
        </Button>
        <span className="text-[10px] uppercase tracking-wider text-flat">
          Market order · instant fill
        </span>
      </div>

      {error && (
        <p role="alert" className="mt-2 text-xs text-down-text" data-testid="trade-error">
          {error}
        </p>
      )}
    </section>
  );
}
