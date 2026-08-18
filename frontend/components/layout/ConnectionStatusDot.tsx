"use client";

import { usePriceStore } from "@/lib/stream/priceStore";
import type { ConnectionStatus } from "@/lib/types";

const LABELS: Record<ConnectionStatus, { text: string; dot: string }> = {
  connecting: { text: "Connecting", dot: "bg-yellow" },
  open: { text: "Live", dot: "bg-up" },
  reconnecting: { text: "Reconnecting", dot: "bg-yellow" },
  closed: { text: "Disconnected", dot: "bg-down" },
};

export function ConnectionStatusDot() {
  const status = usePriceStore((s) => s.connectionStatus);
  const { text, dot } = LABELS[status];

  return (
    <div
      className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-text-muted"
      data-testid="connection-status"
      data-status={status}
    >
      {/* The text label carries the meaning; the dot is decoration, since
          colour alone would exclude some users. */}
      <span className={`h-2 w-2 rounded-full ${dot}`} aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}
