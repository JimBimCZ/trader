"use client";

/** Opens the single EventSource and feeds the price store. */

import { useEffect } from "react";
import { usePriceStore } from "./priceStore";
import type { PriceFrame } from "../types";

export const STREAM_URL = "/api/stream/prices";

/**
 * How long the stream may go quiet before it is reported as stale.
 *
 * EventSource does not fire onerror when a connection stalls — the socket
 * stays open and no data arrives — so without this the UI would claim to be
 * live while showing frozen prices. The threshold sits well above the
 * server's 15s keepalive and Massive's 15s poll, so a genuinely quiet market
 * is not mistaken for a broken one.
 */
export const STALE_AFTER_MS = 20_000;

export function usePriceStream(): void {
  useEffect(() => {
    const { applyFrame, setConnectionStatus } = usePriceStore.getState();

    // Re-announcing "open" on every frame would run a full store notification
    // pass twice a second for a value that has not changed.
    const markOpen = () => {
      if (usePriceStore.getState().connectionStatus !== "open") setConnectionStatus("open");
    };
    const source = new EventSource(STREAM_URL);

    let lastFrameAt = Date.now();

    source.onopen = () => {
      lastFrameAt = Date.now();
      markOpen();
    };

    source.onmessage = (event: MessageEvent<string>) => {
      // Comment frames (the server's keepalive) never reach onmessage, so
      // anything arriving here is a real data frame.
      lastFrameAt = Date.now();
      try {
        applyFrame(JSON.parse(event.data) as PriceFrame);
        markOpen();
      } catch {
        // A malformed frame is dropped; the next one supersedes it anyway.
      }
    };

    const staleTimer = setInterval(() => {
      if (Date.now() - lastFrameAt > STALE_AFTER_MS) {
        setConnectionStatus("reconnecting");
      }
    }, 2_000);

    source.onerror = () => {
      // EventSource reconnects on its own using the server's retry directive,
      // so this reports state rather than rebuilding the connection.
      setConnectionStatus(source.readyState === EventSource.CLOSED ? "closed" : "reconnecting");
    };

    return () => {
      clearInterval(staleTimer);
      source.close();
      setConnectionStatus("closed");
    };
  }, []);
}
