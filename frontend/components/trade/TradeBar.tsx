"use client";

import { useState } from "react";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { useWatchlistStore } from "@/store/useWatchlistStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { formatPrice } from "@/lib/format";
import { Button } from "../ui/Button";
import { SegmentTrack } from "../ui/Segmented";
import { ErrorNote } from "../ui/ErrorNote";

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

  // One price, not the whole map: the ticket re-renders when the symbol it is
  // quoting moves, and stays still the rest of the time.
  const price = usePriceStore((s) =>
    effectiveTicker ? s.prices[effectiveTicker]?.price : undefined,
  );
  const estimate = valid && price ? parsedQuantity * price : null;

  async function submit(side: "buy" | "sell") {
    if (!valid || pending) return;
    if (await trade(effectiveTicker, side, parsedQuantity)) {
      setQuantity("");
    }
  }

  return (
    <section className="rise card px-4 py-3" aria-label="Trade">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1.5">
          <span className="field-label">Symbol</span>
          <input
            value={ticker}
            onChange={(event) => {
              setTicker(event.target.value.toUpperCase());
              if (error) clearError();
            }}
            placeholder={selected ?? "Symbol"}
            maxLength={5}
            aria-label="Ticker to trade"
            data-testid="trade-ticker"
            className="field w-28 font-semibold uppercase tracking-wide placeholder:font-normal placeholder:normal-case"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="field-label">Units</span>
          <input
            value={quantity}
            onChange={(event) => {
              setQuantity(event.target.value);
              if (error) clearError();
            }}
            type="number"
            min="0"
            step="any"
            placeholder="0"
            aria-label="Quantity to trade"
            data-testid="trade-quantity"
            className="field w-28"
          />
        </label>

        <div className="flex flex-col gap-1.5">
          <span className="field-label">Order value</span>
          <span
            className="py-2 text-[15px] font-semibold tracking-[-0.01em] text-text"
            data-testid="trade-estimate"
          >
            {estimate === null ? "—" : formatPrice(estimate)}
          </span>
        </div>

        {/* Sell and Buy are two actions, not two states of one choice, so
            they cannot be a selection — but they are a pair, and the track is
            what says so. Each half stays its own button, keeping its own fill
            and its own direction colour. */}
        <SegmentTrack className="w-full sm:ml-auto sm:w-auto">
          {/* Disabled while a request is in flight, which is all the
              double-submit protection a fake-money demo warrants. */}
          <Button
            variant="sell"
            disabled={!valid || pending}
            onClick={() => submit("sell")}
            data-testid="sell-button"
            className="flex-1 py-1.5 sm:w-24 sm:flex-none"
          >
            Sell
          </Button>
          <Button
            variant="buy"
            disabled={!valid || pending}
            onClick={() => submit("buy")}
            data-testid="buy-button"
            className="flex-1 py-1.5 sm:w-24 sm:flex-none"
          >
            Buy
          </Button>
        </SegmentTrack>
      </div>

      <p className="mt-2.5 text-[11px] text-text-faint">
        Market order, filled instantly at the live price. No fees.
      </p>

      {error && (
        <ErrorNote testId="trade-error" className="mt-2">
          {error}
        </ErrorNote>
      )}
    </section>
  );
}
