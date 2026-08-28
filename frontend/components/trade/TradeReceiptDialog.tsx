"use client";

import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { formatIsoClock, formatPrice, formatQuantity } from "@/lib/format";
import { Button } from "../ui/Button";
import { SignedValue } from "../ui/SignedValue";
import { TickerChip } from "../ui/TickerChip";

/** A fill has happened, so it is named in the past tense -- the same rule the
 *  assistant's inline receipts follow, where an attempt that was rejected
 *  keeps the infinitive. Nothing here can be an attempt: the dialog only
 *  exists once the server has filled the order. */
const VERBS = { buy: "Bought", sell: "Sold" } as const;

function Row({ label, children, testId }: { label: string; children: ReactNode; testId: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2">
      <dt className="text-[12px] text-text-muted">{label}</dt>
      <dd className="text-[13px] font-semibold text-text" data-testid={testId}>
        {children}
      </dd>
    </div>
  );
}

/**
 * What just happened to the user's money, stated once.
 *
 * Fed by `lastTrade`, which only the trade ticket writes: the assistant's
 * trades report themselves inline in the conversation, and a dialog raised by
 * a chat reply would interrupt the user rather than answer them.
 *
 * Every figure comes from the trade response rather than from the portfolio
 * re-read that follows it. The re-read describes the account *now*, which is
 * a different question, and it can fail without the fill being any less real
 * -- the case `f540f1a` was about.
 */
export function TradeReceiptDialog() {
  const receipt = usePortfolioStore((s) => s.lastTrade);
  const dismiss = usePortfolioStore((s) => s.dismissTrade);
  const dialogRef = useRef<HTMLDivElement>(null);

  // `aria-modal` claims the rest of the page is inert, which is only true if
  // focus actually starts in here.
  useEffect(() => {
    if (!receipt) return;
    dialogRef.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, [receipt]);

  if (!receipt) return null;

  // One button, so Tab has nowhere else to go and needs no wrapping of its
  // own -- but Escape does, because a receipt appears after *every* ticket
  // trade and someone placing several in a row should never have to reach for
  // the mouse between them.
  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    dismiss();
  };

  const { ticker, side, quantity, price, position, realizedPnl } = receipt;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4"
      onClick={dismiss}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="trade-receipt-title"
        onKeyDown={handleKeyDown}
        // The backdrop dismisses; a click that lands on the card itself is
        // not a click on the backdrop and must not close it.
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-sm rounded-card bg-surface p-5 shadow-xl"
        data-testid="trade-receipt"
      >
        <div className="flex items-center gap-3">
          <TickerChip ticker={ticker} />
          <div className="min-w-0">
            <h2 id="trade-receipt-title" className="text-[17px] font-semibold text-text">
              {`${VERBS[side]} ${formatQuantity(quantity)} ${ticker}`}
            </h2>
            <p className="text-[12px] text-text-muted">
              Filled at {formatIsoClock(receipt.executedAt)}
            </p>
          </div>
        </div>

        <dl className="mt-4 divide-y divide-separator border-y border-separator">
          <Row label="Fill price" testId="receipt-price">
            {formatPrice(price)}
          </Row>
          <Row label="Order value" testId="receipt-total">
            {formatPrice(quantity * price)}
          </Row>
          {/* Buys realize nothing, and a row reading "—" would invite the
              reader to work out whether that means zero. */}
          {realizedPnl !== null && (
            <Row label="Realized P&L" testId="receipt-realized">
              <SignedValue value={realizedPnl} />
            </Row>
          )}
          <Row label="Position" testId="receipt-position">
            {position
              ? `${formatQuantity(position.quantity)} @ ${formatPrice(position.avgCost)}`
              : "Closed"}
          </Row>
          <Row label="Cash balance" testId="receipt-cash">
            {formatPrice(receipt.cashBalance)}
          </Row>
        </dl>

        <div className="mt-5 flex justify-end">
          <Button type="button" variant="prominent" onClick={dismiss}>
            Done
          </Button>
        </div>
      </div>
    </div>
  );
}
