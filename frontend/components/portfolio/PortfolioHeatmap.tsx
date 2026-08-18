"use client";

import { Treemap, ResponsiveContainer } from "recharts";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { valueHolding } from "@/lib/portfolio";
import { colors } from "@/lib/theme";
import { directionGlyph, formatSignedPercent } from "@/lib/format";
import { CHART_MIN_H } from "../layout/panels";

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

/**
 * How saturated that colour is drawn.
 *
 * Capped below full strength so the dark label keeps 4.5:1 even on the
 * deepest loss cell — on a white surface the fill is what dictates the text
 * contrast, not the other way round.
 */
export function pnlOpacity(pctChange: number): number {
  const magnitude = Math.min(Math.abs(pctChange), 10) / 10;
  return 0.35 + magnitude * 0.55;
}

interface CellProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  depth?: number;
  ticker?: string;
  pct?: number;
  weight?: number;
}

function Cell({
  x = 0,
  y = 0,
  width = 0,
  height = 0,
  depth = 1,
  ticker = "",
  pct = 0,
  weight = 0,
}: CellProps) {
  // Recharts invokes the content renderer for the root node too. Drawing it
  // would stack a second rectangle and label on top of the real cells.
  if (depth === 0) return null;

  const showLabel = width > 48 && height > 32;
  // The return only earns its line once the weight already has one — on a
  // freshly opened portfolio every return is ~0% and the weight is the number
  // actually worth reading.
  const showReturn = showLabel && height > 52;
  return (
    <g>
      <rect
        x={x + 1.5}
        y={y + 1.5}
        width={Math.max(width - 3, 0)}
        height={Math.max(height - 3, 0)}
        rx={10}
        fill={pnlToColor(pct)}
        fillOpacity={pnlOpacity(pct)}
        stroke={colors.surface}
        strokeWidth={2}
      />
      {showLabel && (
        <>
          <text x={x + 10} y={y + 20} fill={colors.text} fontSize={12} fontWeight={700}>
            {ticker}
          </text>
          {/* Weight, then return. The arrow is what tells them apart — the
              same glyph that marks a change everywhere else in the app — so
              neither line needs a label that would overflow a narrow cell. */}
          <text x={x + 10} y={y + 35} fill={colors.text} fontSize={11} opacity={0.6}>
            {weight.toFixed(1)}%
          </text>
          {/* The signed percentage is always drawn: colour alone is not a
              sufficient encoding of gain versus loss. */}
          {showReturn && (
            <text x={x + 10} y={y + 50} fill={colors.text} fontSize={11} fontWeight={600}>
              {`${directionGlyph(pct)} ${formatSignedPercent(pct)}`}
            </text>
          )}
        </>
      )}
    </g>
  );
}

export function PortfolioHeatmap() {
  const positions = usePortfolioStore((s) => s.positions);
  const livePrices = usePriceStore((s) => s.prices);

  // Weighted against invested value rather than the account total: this is a
  // map of the portfolio, and cash has no rectangle on it.
  let invested = 0;
  const sized = positions.map((position) => {
    const { pctChange, value } = valueHolding(position, livePrices);
    // A floor keeps a near-worthless holding addressable rather than collapsing
    // its rectangle to nothing.
    const size = Math.max(value, 0.01);
    invested += size;
    return { name: position.ticker, ticker: position.ticker, size, pct: pctChange };
  });

  const data = sized.map((item) => ({
    ...item,
    weight: invested ? (item.size / invested) * 100 : 0,
  }));

  return (
    <section
      className={`rise card flex ${CHART_MIN_H} flex-col lg:min-h-0`}
      aria-label="Portfolio heatmap"
    >
      <header className="card-title">
        <span>Allocation &amp; P&amp;L</span>
      </header>
      <div className="min-h-0 flex-1 p-2" data-testid="heatmap">
        {data.length === 0 ? (
          <p className="flex h-full items-center justify-center px-4 text-center text-sm text-text-muted">
            Positions appear here, sized by weight and shaded by return.
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
