"use client";

import { Treemap, ResponsiveContainer } from "recharts";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { valueHolding } from "@/lib/portfolio";
import { usePalette } from "@/lib/useTheme";
import { palettes, type Palette } from "@/lib/theme";
import { directionGlyph, formatSignedPercent } from "@/lib/format";
import { CHART_MIN_H } from "../layout/panels";

/**
 * Maps a position's return to a colour on the loss-neutral-profit scale.
 *
 * Saturates at ±10% so one runaway position does not flatten every other cell
 * to the same neutral grey.
 */
export function pnlToColor(pctChange: number, palette: Palette = palettes.light): string {
  const { colors } = palette;
  const clamped = Math.max(-10, Math.min(10, pctChange)) / 10;
  if (Math.abs(clamped) < 0.02) return colors.heatmapNeutral;
  return clamped > 0 ? colors.heatmapProfitDeep : colors.heatmapLossDeep;
}

/** Capped below full strength so the label keeps 4.5:1 on the deepest cell. */
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
  palette?: Palette;
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
  palette = palettes.light,
}: CellProps) {
  const { colors } = palette;
  // Recharts invokes the content renderer for the root node too, which would
  // stack a second rectangle and label on top of the real cells.
  if (depth === 0) return null;

  const showLabel = width > 48 && height > 32;
  // On a freshly opened portfolio every return is ~0%, so the weight is the
  // line worth keeping when only one fits.
  const showReturn = showLabel && height > 52;
  return (
    <g>
      <rect
        x={x + 1.5}
        y={y + 1.5}
        width={Math.max(width - 3, 0)}
        height={Math.max(height - 3, 0)}
        rx={12}
        fill={pnlToColor(pct, palette)}
        fillOpacity={pnlOpacity(pct)}
        stroke={colors.surface}
        strokeWidth={2}
      />
      {showLabel && (
        <>
          <text x={x + 10} y={y + 20} fill={colors.text} fontSize={12} fontWeight={700}>
            {ticker}
          </text>
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
  const palette = usePalette();
  const positions = usePortfolioStore((s) => s.positions);
  const livePrices = usePriceStore((s) => s.prices);

  // Weighted against invested value rather than the account total: cash has
  // no rectangle on this map.
  let invested = 0;
  const sized = positions.map((position) => {
    const { pctChange, value } = valueHolding(position, livePrices);
    // A floor keeps a near-worthless holding addressable.
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
              content={<Cell palette={palette} />}
            />
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
