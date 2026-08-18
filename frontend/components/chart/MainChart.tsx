"use client";

import { useEffect, useRef } from "react";
import { createChart, type IChartApi, type ISeriesApi, ColorType } from "lightweight-charts";
import { usePriceStore } from "@/lib/stream/priceStore";
import { fetchHistory } from "@/lib/api/endpoints";
import { colors } from "@/lib/theme";

/**
 * The detailed price chart for the selected ticker.
 *
 * Live ticks are pushed straight into the series from a store subscription
 * rather than through React state: this is the one path hot enough that going
 * through reconciliation twice a second would be wasteful. Everything else in
 * the app stays declarative.
 */
export function MainChart({ ticker }: { ticker: string | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Area"> | null>(null);

  useEffect(() => {
    if (!containerRef.current || !ticker) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: colors.bgAlt },
        textColor: colors.textMuted,
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      },
      grid: {
        vertLines: { color: colors.border },
        horzLines: { color: colors.border },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: { borderColor: colors.border, timeVisible: true, secondsVisible: true },
      crosshair: { mode: 0 },
      autoSize: true,
    });

    const series = chart.addAreaSeries({
      lineColor: colors.accentBlue,
      topColor: `${colors.accentBlue}55`,
      bottomColor: `${colors.accentBlue}05`,
      lineWidth: 2,
      priceLineColor: colors.accentYellow,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    let cancelled = false;
    let lastTime = 0;

    // Seed from the server ring buffer so the chart has shape immediately
    // rather than drawing itself over the next few seconds.
    fetchHistory(ticker)
      .then((points) => {
        if (cancelled || points.length === 0) return;

        // The buffer ticks twice a second but the series is keyed by whole
        // seconds, so collapse each second to its latest price. Passing the
        // raw points would hand the series duplicate timestamps, which it
        // rejects outright — taking the whole chart down with it.
        const bySecond = new Map<number, number>();
        for (const point of points) {
          bySecond.set(Math.floor(point.timestamp), point.price);
        }

        const seeded = [...bySecond.entries()]
          .sort((a, b) => a[0] - b[0])
          .map(([time, value]) => ({ time: time as never, value }));

        series.setData(seeded);
        lastTime = bySecond.size ? Math.max(...bySecond.keys()) : 0;
        chart.timeScale().fitContent();
      })
      .catch(() => {
        // A ticker with no history yet simply starts empty and fills in.
      });
    const unsubscribe = usePriceStore.subscribe(
      (state) => state.prices[ticker],
      (snapshot) => {
        if (!snapshot) return;
        const time = Math.floor(snapshot.timestamp);
        // Updating at or after the last point is fine — an equal timestamp
        // replaces that second's value. Going backwards is not, and would
        // throw, so it is dropped.
        if (time < lastTime) return;
        lastTime = time;
        try {
          series.update({ time: time as never, value: snapshot.price });
        } catch {
          // The series is disposed mid-teardown; the next mount reseeds.
        }
      },
    );

    return () => {
      cancelled = true;
      unsubscribe();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [ticker]);

  return (
    <section className="panel flex min-h-0 flex-1 flex-col" aria-label="Price chart">
      <header className="panel-title flex items-center justify-between">
        <span>{ticker ? `${ticker} — price` : "Price"}</span>
      </header>
      {ticker ? (
        <div ref={containerRef} className="min-h-0 flex-1" data-testid="main-chart" />
      ) : (
        <p className="flex flex-1 items-center justify-center text-xs text-text-muted">
          Select a ticker to chart it.
        </p>
      )}
    </section>
  );
}
