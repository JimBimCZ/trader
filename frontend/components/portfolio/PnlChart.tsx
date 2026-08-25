"use client";

import { useEffect } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { usePalette } from "@/lib/useTheme";
import { radii } from "@/lib/theme";
import { formatCompact, formatIsoClock, formatPrice } from "@/lib/format";
import { SignedValue } from "../ui/SignedValue";
import { CHART_MIN_H } from "../layout/panels";
import { Skeleton } from "../ui/Skeleton";

/**
 * Whole dollars are unreadable when the series spans a few dollars — every
 * tick renders as the same number — so the precision follows the range.
 */
function axisFormatter(range: number) {
  return (value: number) => (range < 50 ? formatPrice(value) : formatCompact(value));
}

/**
 * Recharts reserves the Y axis band before it draws and clips whatever does
 * not fit, so the band has to be sized for the longest label it will actually
 * render. A constant cannot do that: under the `formatPrice` branch above,
 * `$998.00` and `$250,002.00` differ by 22px, and the card is only ~275px
 * wide — a band wide enough for the second wastes a tenth of the plot on the
 * first.
 *
 * The glyphs are tabular (stated once on `body`), so at `fontSize: 10` they
 * measure ~5.7px each; the +8 is the gap to the plot. Clamped at both ends so
 * an outlandish value cannot eat the chart.
 */
export function axisWidth(values: number[], range: number): number {
  const format = axisFormatter(range);
  const longest = values.reduce((widest, value) => Math.max(widest, format(value).length), 0);
  return Math.min(76, Math.max(44, Math.ceil(longest * 5.7) + 8));
}

/**
 * Total portfolio value over time. Snapshots arrive every 30 seconds, so this
 * is declarative SVG rather than canvas.
 */
export function PnlChart() {
  const { colors, shadows } = usePalette();
  const history = usePortfolioStore((s) => s.history);
  const loaded = usePortfolioStore((s) => s.loaded);
  const refreshHistory = usePortfolioStore((s) => s.refreshHistory);

  useEffect(() => {
    refreshHistory();
    const timer = setInterval(refreshHistory, 30_000);
    return () => clearInterval(timer);
  }, [refreshHistory]);

  const data = history.map((point) => ({
    time: formatIsoClock(point.recordedAt),
    value: point.totalValue,
  }));

  const first = data[0]?.value ?? 0;
  const last = data[data.length - 1]?.value ?? 0;
  const up = last >= first;
  const stroke = up ? colors.up : colors.down;

  const values = data.map((point) => point.value);
  const range = values.length ? Math.max(...values) - Math.min(...values) : 0;

  return (
    <section
      className={`rise card flex ${CHART_MIN_H} flex-col lg:min-h-0`}
      aria-label="Portfolio value over time"
    >
      <header className="card-title">
        <span>Performance</span>
        {data.length >= 2 && (
          <span className="text-[11px] font-semibold">
            <SignedValue value={last - first} /> this session
          </span>
        )}
      </header>
      <div className="min-h-0 flex-1 p-2" data-testid="pnl-chart">
        {!loaded ? (
          <Skeleton className="h-full w-full rounded-[10px]" />
        ) : data.length < 2 ? (
          <p className="flex h-full items-center justify-center px-4 text-center text-sm text-text-muted">
            Charting starts once the first two snapshots land, about a minute in.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="pnl-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.26} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="time"
                tick={{ fill: colors.textMuted, fontSize: 10 }}
                axisLine={{ stroke: colors.border }}
                tickLine={false}
                minTickGap={40}
              />
              <YAxis
                domain={["auto", "auto"]}
                tick={{ fill: colors.textMuted, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={axisWidth(values, range)}
                tickFormatter={axisFormatter(range)}
              />
              <Tooltip
                contentStyle={{
                  background: colors.surface,
                  border: `1px solid ${colors.border}`,
                  borderRadius: parseInt(radii.control, 10),
                  boxShadow: shadows.pop,
                  fontSize: 12,
                }}
                labelStyle={{ color: colors.textMuted }}
                formatter={(value: number) => [formatPrice(value), "Value"]}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={stroke}
                strokeWidth={2}
                fill="url(#pnl-fill)"
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
