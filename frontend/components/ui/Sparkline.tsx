"use client";

import { useMemo } from "react";
import { usePriceStore } from "@/lib/stream/priceStore";
import { colors } from "@/lib/theme";

/**
 * A hand-drawn SVG polyline.
 *
 * A charting library instance per row would carry its own observers and
 * render loop; at 25 rows that overhead buys nothing for a line with no axes,
 * labels, or interaction.
 */
export function Sparkline({ ticker, width = 72, height = 20 }: {
  ticker: string;
  width?: number;
  height?: number;
}) {
  const points = usePriceStore((state) => state.sparklines[ticker]);

  const path = useMemo(() => {
    if (!points || points.length < 2) return null;

    const min = Math.min(...points);
    const max = Math.max(...points);
    const range = max - min || 1;
    const step = width / (points.length - 1);

    return points
      .map((value, index) => {
        const x = index * step;
        const y = height - ((value - min) / range) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [points, width, height]);

  if (!path || !points) {
    return <svg width={width} height={height} aria-hidden="true" />;
  }

  const rising = points[points.length - 1] >= points[0];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${ticker} recent price trend, ${rising ? "rising" : "falling"}`}
      data-testid={`sparkline-${ticker}`}
    >
      <polyline
        points={path}
        fill="none"
        stroke={rising ? colors.up : colors.down}
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
