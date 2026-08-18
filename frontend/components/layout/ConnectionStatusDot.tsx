"use client";

import { usePriceStore } from "@/lib/stream/priceStore";
import type { ConnectionStatus } from "@/lib/types";

const LABELS: Record<ConnectionStatus, { text: string; dot: string; skin: string }> = {
  connecting: { text: "Connecting", dot: "bg-yellow", skin: "bg-yellow-wash text-yellow-text" },
  open: { text: "Live", dot: "bg-brand", skin: "bg-brand-wash text-up-text" },
  reconnecting: { text: "Reconnecting", dot: "bg-yellow", skin: "bg-yellow-wash text-yellow-text" },
  closed: { text: "Disconnected", dot: "bg-down", skin: "bg-down-wash text-down-text" },
};

export function ConnectionStatusDot() {
  const status = usePriceStore((s) => s.connectionStatus);
  const { text, dot, skin } = LABELS[status];

  return (
    <div
      className={`flex items-center gap-2 rounded-full px-3 py-1.5 font-display text-[11px] font-bold tracking-tight ${skin}`}
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
