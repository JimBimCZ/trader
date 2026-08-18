"use client";

import { usePriceStore } from "@/lib/stream/priceStore";
import type { ConnectionStatus } from "@/lib/types";

const LABELS: Record<ConnectionStatus, { text: string; dot: string; skin: string }> = {
  connecting: { text: "Connecting", dot: "bg-yellow", skin: "bg-yellow-wash text-yellow-text" },
  open: { text: "Live", dot: "bg-up", skin: "bg-up-wash text-up-text" },
  reconnecting: { text: "Reconnecting", dot: "bg-yellow", skin: "bg-yellow-wash text-yellow-text" },
  closed: { text: "Disconnected", dot: "bg-down", skin: "bg-down-wash text-down-text" },
};

export function ConnectionStatusDot() {
  const status = usePriceStore((s) => s.connectionStatus);
  const { text, dot, skin } = LABELS[status];

  return (
    <div
      className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold tracking-[-0.01em] ${skin}`}
      data-testid="connection-status"
      data-status={status}
    >
      {/* The text label carries the meaning; the dot is decoration, since
          colour alone would exclude some users. */}
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}
