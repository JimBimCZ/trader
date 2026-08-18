"use client";

import { useId, useMemo } from "react";
import { usePriceStore } from "@/lib/stream/priceStore";
import { usePalette } from "@/lib/useTheme";

/**
 * A hand-drawn SVG area.
 *
 * A charting library instance per row would carry its own observers and
 * render loop; at 25 rows that overhead buys nothing for a line with no axes,
 * labels, or interaction. The fill under the line is what makes it read as a
 * chart rather than a scribble at this size.
 */
const WIDTH = 52;
const HEIGHT = 26;

export function Sparkline({ ticker }: { ticker: string }) {
  const points = usePriceStore((state) => state.sparklines[ticker]);
  const { colors } = usePalette();
  const gradientId = useId();

  const line = useMemo(() => {
    if (!points || points.length < 2) return null;

    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = max - min || 1;
    const step = WIDTH / (points.length - 1);
    // Inset vertically so the stroke is not clipped at the extremes.
    const top = 2;
    const usable = HEIGHT - 4;

    return points
      .map((value, index) => {
        const x = index * step;
        const y = top + (1 - (value - min) / range) * usable;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [points]);

  if (!line || !points) {
    return <svg width={WIDTH} height={HEIGHT} aria-hidden="true" />;
  }

  const rising = points[points.length - 1] >= points[0];
  const stroke = rising ? colors.up : colors.down;

  return (
    <svg
      width={WIDTH}
      height={HEIGHT}
      viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
      role="img"
      aria-label={`${ticker} recent price trend, ${rising ? "rising" : "falling"}`}
      data-testid={`sparkline-${ticker}`}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.3} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={`${line} ${WIDTH},${HEIGHT} 0,${HEIGHT}`} fill={`url(#${gradientId})`} />
      <polyline
        points={line}
        fill="none"
        stroke={stroke}
        strokeWidth="1.75"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
