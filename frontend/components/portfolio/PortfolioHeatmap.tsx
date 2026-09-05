"use client";

import { useState } from "react";
import { Treemap, ResponsiveContainer } from "recharts";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { usePriceStore } from "@/lib/stream/priceStore";
import { valueHolding } from "@/lib/portfolio";
import { usePalette } from "@/lib/useTheme";
import { instrumentColor, palettes, type Palette } from "@/lib/theme";
import {
  directionGlyph,
  formatCompact,
  formatPrice,
  formatSignedPercent,
} from "@/lib/format";
import { CHART_MIN_H } from "../layout/panels";
import { Skeleton } from "../ui/Skeleton";
import { LoadFailure } from "../ui/LoadFailure";

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
  amount?: number;
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
  amount = 0,
  palette = palettes.light,
}: CellProps) {
  const [hovered, setHovered] = useState(false);
  const { colors, appearance } = palette;
  // Recharts invokes the content renderer for the root node too, which would
  // stack a second rectangle and label on top of the real cells.
  if (depth === 0) return null;

  const w = Math.max(width - 3, 0);
  const h = Math.max(height - 3, 0);
  const base = pnlOpacity(pct);
  const fill = pnlToColor(pct, palette);
  // A flat wash reads as a placeholder block. Lit from the top, the same
  // colour reads as a surface — and the gradient is per cell because its two
  // stops are that cell's own opacity.
  const gradient = `heat-${ticker || "cell"}`;

  const showLabel = w > 48 && h > 32;
  // On a freshly opened portfolio every return is ~0%, so the weight is the
  // line worth keeping when only one fits.
  const showFooter = showLabel && h > 58;
  const showAmount = showFooter && w > 108;

  return (
    <g
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ cursor: "default" }}
    >
      <title>{`${ticker} — ${formatPrice(amount)}, ${weight.toFixed(1)}% of holdings, ${formatSignedPercent(pct)}`}</title>
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={fill} stopOpacity={Math.min(base * 1.2, 1)} />
          <stop offset="100%" stopColor={fill} stopOpacity={base * 0.62} />
        </linearGradient>
      </defs>
      <rect
        x={x + 1.5}
        y={y + 1.5}
        width={w}
        height={h}
        rx={12}
        fill={`url(#${gradient})`}
        stroke={hovered ? colors.text : colors.surface}
        strokeOpacity={hovered ? 0.45 : 1}
        strokeWidth={2}
      />
      {showLabel && (
        <>
          {/* The identity colour that follows this holding through the
              watchlist, the table and the main chart. The cell's own colour
              is spoken for by the return. */}
          <circle cx={x + 13} cy={y + 17} r={3.5} fill={instrumentColor(ticker, appearance)} />
          <text x={x + 22} y={y + 21} fill={colors.text} fontSize={13} fontWeight={700}>
            {ticker}
          </text>
          <text
            x={x + w - 8}
            y={y + 21}
            textAnchor="end"
            fill={colors.text}
            fontSize={11}
            opacity={0.6}
          >
            {weight.toFixed(1)}%
          </text>
          {/* Anchored to the floor of the cell rather than stacked under the
              ticker, so cells of different heights read as one grid. The
              signed percentage is always drawn: colour alone is not a
              sufficient encoding of gain versus loss. */}
          {showFooter && (
            <text
              x={x + 13}
              y={y + h - 8}
              fill={colors.text}
              fontSize={12}
              fontWeight={600}
            >
              {`${directionGlyph(pct)} ${formatSignedPercent(pct)}`}
            </text>
          )}
          {showAmount && (
            <text
              x={x + w - 8}
              y={y + h - 8}
              textAnchor="end"
              fill={colors.text}
              fontSize={11}
              opacity={0.6}
            >
              {formatCompact(amount)}
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
  const status = usePortfolioStore((s) => s.status);
  const refresh = usePortfolioStore((s) => s.refresh);
  const livePrices = usePriceStore((s) => s.prices);

  // Weighted against invested value rather than the account total: cash has
  // no rectangle on this map.
  let invested = 0;
  const sized = positions.map((position) => {
    const { pctChange, value } = valueHolding(position, livePrices);
    // A floor keeps a near-worthless holding addressable.
    const size = Math.max(value, 0.01);
    invested += size;
    return {
      name: position.ticker,
      ticker: position.ticker,
      size,
      amount: value,
      pct: pctChange,
    };
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
        {data.length > 0 && (
          <span className="text-[11px] font-normal text-text-muted">
            {formatCompact(invested)} invested
          </span>
        )}
      </header>
      <div className="min-h-0 flex-1 p-2" data-testid="heatmap">
        {status === "pending" ? (
          <Skeleton className="h-full w-full rounded-[10px]" />
        ) : status === "failed" ? (
          <LoadFailure what="your positions" onRetry={refresh} className="h-full" />
        ) : data.length === 0 ? (
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
