"use client";

import { Treemap, ResponsiveContainer } from "recharts";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { colors } from "@/lib/theme";
import { formatSignedPercent } from "@/lib/format";

/**
 * Maps a position's return to a colour on the loss-neutral-profit scale.
 *
 * Saturates at ±10% so one runaway position does not flatten every other
 * cell to the same neutral grey. Exported for direct unit testing — this is
 * the risky part, not Recharts' rendering.
 */
export function pnlToColor(pctChange: number): string {
  const clamped = Math.max(-10, Math.min(10, pctChange)) / 10;
  if (Math.abs(clamped) < 0.02) return colors.heatmapNeutral;
  return clamped > 0 ? colors.heatmapProfitDeep : colors.heatmapLossDeep;
}

export function pnlOpacity(pctChange: number): number {
  const magnitude = Math.min(Math.abs(pctChange), 10) / 10;
  return 0.35 + magnitude * 0.65;
}

interface CellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  ticker?: string;
  pct?: number;
}

function Cell({ x = 0, y = 0, width = 0, height = 0, depth = 1, ticker = "", pct = 0 }: CellProps) {
  // Recharts invokes the content renderer for the root node too. Drawing it
  // would stack a second rectangle and label on top of the real cells.
  if (depth === 0) return null;

  const showLabel = width > 44 && height > 28;
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={pnlToColor(pct)}
        fillOpacity={pnlOpacity(pct)}
        stroke={colors.bg}
        strokeWidth={2}
      />
      {showLabel && (
        <>
          <text x={x + 6} y={y + 16} fill={colors.text} fontSize={11} fontWeight={600}>
            {ticker}
          </text>
          {/* The signed percentage is always drawn: colour alone is not a
              sufficient encoding of gain versus loss. */}
          <text x={x + 6} y={y + 30} fill={colors.text} fontSize={10} opacity={0.9}>
            {formatSignedPercent(pct)}
          </text>
        </>
      )}
    </g>
  );
}

export function PortfolioHeatmap() {
  const positions = usePortfolioStore((s) => s.positions);
  const livePrices = usePriceStore((s) => s.prices);

  const data = positions.map((position) => {
    const price = livePrices[position.ticker]?.price ?? position.currentPrice;
    const pct = position.avgCost ? ((price - position.avgCost) / position.avgCost) * 100 : 0;
    return {
      name: position.ticker,
      ticker: position.ticker,
      size: Math.max(position.quantity * price, 0.01),
      pct,
    };
  });

  return (
    <section className="panel flex min-h-0 flex-col" aria-label="Portfolio heatmap">
      <header className="panel-title">Allocation &amp; P&amp;L</header>
      <div className="min-h-0 flex-1 p-1" data-testid="heatmap">
        {data.length === 0 ? (
          <p className="flex h-full items-center justify-center text-xs text-text-muted">
            No positions to map.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <Treemap
              data={data}
              dataKey="size"
              isAnimationActive={false}
              content={<Cell />}
            />
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
