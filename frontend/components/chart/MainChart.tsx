"use client";

import { memo, useEffect, useRef } from "react";
import { createChart, ColorType } from "lightweight-charts";
import { usePriceStore } from "@/lib/stream/priceStore";
import { fetchHistory } from "@/lib/api/endpoints";
import { instrumentColor } from "@/lib/theme";
import { usePalette } from "@/lib/useTheme";
import { formatClockSeconds } from "@/lib/format";
import { PriceCell } from "../ui/PriceCell";
import { ChangeBadge } from "../ui/ChangeBadge";
import { InstrumentLabel } from "../ui/InstrumentLabel";
import { PANELS } from "../layout/panels";

const LiveChange = memo(function LiveChange({ ticker }: { ticker: string }) {
  const dailyChange = usePriceStore((s) => s.prices[ticker]?.dailyChangePercent ?? 0);
  return <ChangeBadge value={dailyChange} pill />;
});

export function MainChart({ ticker }: { ticker: string | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { appearance, colors } = usePalette();

  useEffect(() => {
    if (!containerRef.current || !ticker) return;

    // A canvas font string cannot name a font stack the way CSS can, so the
    // resolved family is read off the document once per mount.
    const bodyFont = getComputedStyle(document.body).fontFamily || "system-ui";

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: colors.surface },
        textColor: colors.textMuted,
        fontFamily: `${bodyFont}, system-ui, sans-serif`,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: colors.border },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: {
        borderVisible: false,
        timeVisible: true,
        secondsVisible: true,
        // The series is keyed by UTC seconds, which the axis would otherwise
        // label in UTC — a different clock from the portfolio chart beside it.
        tickMarkFormatter: formatClockSeconds,
      },
      localization: { timeFormatter: formatClockSeconds },
      crosshair: { mode: 0 },
      autoSize: true,
    });

    // Selecting a ticker recolours the chart to match the row that was
    // clicked, and green stays reserved for "up".
    const tint = instrumentColor(ticker, appearance);
    const series = chart.addAreaSeries({
      lineColor: tint,
      topColor: `${tint}38`,
      bottomColor: `${tint}00`,
      lineWidth: 2,
      priceLineColor: colors.textFaint,
    });

    let cancelled = false;
    let lastTime = 0;

    // Seed from the server ring buffer so the chart has shape immediately.
    fetchHistory(ticker)
      .then((points) => {
        if (cancelled || points.length === 0) return;

        // The buffer ticks twice a second but the series is keyed by whole
        // seconds. Duplicate timestamps are rejected outright by the series,
        // so collapse each second to its latest price.
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
        // An equal timestamp replaces that second's value; going backwards
        // would throw, so it is dropped.
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
    };
    // The canvas holds its colours rather than reading them, so switching
    // appearance has to rebuild it.
  }, [ticker, appearance, colors]);

  const shell = `rise card flex ${PANELS.chart.minH} flex-1 flex-col lg:min-h-0`;

  if (!ticker) {
    return (
      <section id={PANELS.chart.id} className={shell} aria-label="Price chart">
        <header className="card-title">
          <span>{PANELS.chart.label}</span>
        </header>
        <p className="flex flex-1 items-center justify-center text-sm text-text-muted">
          Pick a symbol from the watchlist to chart it.
        </p>
      </section>
    );
  }

  return (
    <section id={PANELS.chart.id} className={shell} aria-label="Price chart">
      <header className="card-title">
        <InstrumentLabel ticker={ticker} />
        <span className="flex items-center gap-2">
          <PriceCell ticker={ticker} className="text-base" testId={`chart-price-${ticker}`} />
          <LiveChange ticker={ticker} />
        </span>
      </header>
      <div ref={containerRef} className="min-h-0 flex-1 px-1 pb-1" data-testid="main-chart" />
    </section>
  );
}
