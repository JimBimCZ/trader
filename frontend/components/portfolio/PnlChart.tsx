"use client";

import { useEffect } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePortfolioStore } from "@/store/usePortfolioStore";
import { usePalette } from "@/lib/useTheme";
import { formatCompact, formatIsoClock, formatPrice } from "@/lib/format";
import { SignedValue } from "../ui/SignedValue";
import { ChangeBadge } from "../ui/ChangeBadge";
import { CHART_MIN_H } from "../layout/panels";
import { Skeleton } from "../ui/Skeleton";
import { LoadFailure } from "../ui/LoadFailure";

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
 * A portfolio drifts by tenths of a percent over a session, so `["auto",
 * "auto"]` — which pins the extremes to the plot edges — draws that drift as a
 * canyon touching both walls. Padding the domain gives the line somewhere to
 * sit, and keeps the baseline rule visible when the whole series is above or
 * below it.
 */
export function valueDomain(values: number[], baseline: number): [number, number] {
  if (!values.length) return [0, 1];
  const low = Math.min(baseline, ...values);
  const high = Math.max(baseline, ...values);
  // A flat series has no range to take a fraction of; fall back to something
  // proportional to the account so the line lands mid-plot rather than on an
  // edge.
  const pad = high - low || Math.max(Math.abs(high) * 0.001, 0.5);
  return [low - pad * 0.18, high + pad * 0.18];
}

/** The app's own card, rather than Recharts' default white box. */
function ValueTooltip({
  active,
  payload,
  label,
  baseline,
}: {
  active?: boolean;
  payload?: { value?: number }[];
  label?: string;
  baseline: number;
}) {
  const value = payload?.[0]?.value;
  if (!active || typeof value !== "number") return null;
  return (
    <div className="card px-3 py-2 shadow-pop">
      <p className="text-[11px] text-text-muted">{label}</p>
      <p className="text-[15px] font-semibold tracking-[-0.02em] text-text">
        {formatPrice(value)}
      </p>
      <SignedValue value={value - baseline} className="text-[11px] font-semibold" />
    </div>
  );
}

/**
 * Total portfolio value over time. Snapshots arrive every 30 seconds, so this
 * is declarative SVG rather than canvas.
 */
export function PnlChart() {
  const { colors } = usePalette();
  const history = usePortfolioStore((s) => s.history);
  // `historyStatus`, not `status`: this chart draws `history`, which comes
  // from its own endpoint fetched in the effect below -- while `status`
  // tracks GET /api/portfolio, which `useAppBoot` resolves earlier. Gating on
  // the latter let "Charting starts once the first two snapshots land" render
  // over history nobody had fetched yet.
  const historyStatus = usePortfolioStore((s) => s.historyStatus);
  const refreshHistory = usePortfolioStore((s) => s.refreshHistory);

  useEffect(() => {
    // Swallowed, not ignored: `refreshHistory` records the outcome on the
    // store, which is what the render below reads. Letting it reject here
    // would only raise an unhandled rejection saying the same thing.
    const load = () => void refreshHistory().catch(() => {});
    load();
    const timer = setInterval(load, 30_000);
    return () => clearInterval(timer);
  }, [refreshHistory]);

  const data = history.map((point) => ({
    time: formatIsoClock(point.recordedAt),
    value: point.totalValue,
  }));

  const first = data[0]?.value ?? 0;
  const last = data[data.length - 1]?.value ?? 0;
  const change = last - first;
  const up = change >= 0;
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
          <span className="flex items-center gap-2 text-[11px] font-semibold">
            <span className="font-normal text-text-muted">Session</span>
            <SignedValue value={change} />
            <ChangeBadge value={first ? (change / first) * 100 : 0} pill />
          </span>
        )}
      </header>
      <div className="min-h-0 flex-1 p-2" data-testid="pnl-chart">
        {historyStatus === "pending" ? (
          <Skeleton className="h-full w-full rounded-[10px]" />
        ) : historyStatus === "failed" ? (
          <LoadFailure what="the value history" onRetry={refreshHistory} className="h-full" />
        ) : data.length < 2 ? (
          <p className="flex h-full items-center justify-center px-4 text-center text-sm text-text-muted">
            Charting starts once the first two snapshots land, about a minute in.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="pnl-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.3} />
                  <stop offset="55%" stopColor={stroke} stopOpacity={0.1} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0} />
                </linearGradient>
              </defs>
              {/* Recessive by design: the rules are there to read a value
                  off, not to be looked at. */}
              <CartesianGrid
                vertical={false}
                stroke={colors.border}
                strokeOpacity={0.7}
                strokeDasharray="2 4"
              />
              <XAxis
                dataKey="time"
                tick={{ fill: colors.textMuted, fontSize: 10 }}
                axisLine={{ stroke: colors.border }}
                tickLine={false}
                minTickGap={40}
              />
              <YAxis
                domain={valueDomain(values, first)}
                tick={{ fill: colors.textMuted, fontSize: 10 }}
                axisLine={false}
                tickLine={false}
                width={axisWidth(values, range)}
                tickFormatter={axisFormatter(range)}
              />
              {/* Where the session opened. Without it the area is a shape;
                  with it, every point above the rule is a gain. */}
              <ReferenceLine
                y={first}
                stroke={colors.textFaint}
                strokeDasharray="4 4"
                strokeWidth={1}
              />
              <Tooltip
                cursor={{ stroke: colors.borderStrong, strokeWidth: 1 }}
                content={<ValueTooltip baseline={first} />}
              />
              <Area
                type="monotone"
                dataKey="value"
                stroke={stroke}
                strokeWidth={2}
                fill="url(#pnl-fill)"
                dot={false}
                activeDot={{ r: 4, fill: stroke, stroke: colors.surface, strokeWidth: 2 }}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}
