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
import { colors } from "@/lib/theme";
import { formatCompact, formatPrice } from "@/lib/format";

/**
 * Whole dollars are unreadable when the whole series spans a few dollars —
 * every tick renders as the same number — so the precision follows the range.
 */
function axisFormatter(range: number) {
  return (value: number) =>
    range < 50
      ? `$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : formatCompact(value);
}

/**
 * Total portfolio value over time.
 *
 * Snapshots arrive every 30 seconds, so this is declarative SVG rather than
 * canvas — there is no update-rate problem to solve here.
 */
export function PnlChart() {
  const history = usePortfolioStore((s) => s.history);
  const refreshHistory = usePortfolioStore((s) => s.refreshHistory);

  useEffect(() => {
    refreshHistory();
    const timer = setInterval(refreshHistory, 30_000);
    return () => clearInterval(timer);
  }, [refreshHistory]);

  const data = history.map((point) => ({
    time: new Date(point.recordedAt).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    }),
    value: point.totalValue,
  }));

  const first = data[0]?.value ?? 0;
  const last = data[data.length - 1]?.value ?? 0;
  const up = last >= first;
  const stroke = up ? colors.up : colors.down;

  const values = data.map((point) => point.value);
  const range = values.length ? Math.max(...values) - Math.min(...values) : 0;

  return (
    <section className="panel flex min-h-0 flex-col" aria-label="Portfolio value over time">
      <header className="panel-title">Portfolio value</header>
      <div className="min-h-0 flex-1 p-2" data-testid="pnl-chart">
        {data.length < 2 ? (
          <p className="flex h-full items-center justify-center text-xs text-text-muted">
            Collecting data…
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
              <defs>
                <linearGradient id="pnl-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={stroke} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={stroke} stopOpacity={0.02} />
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
                width={72}
                tickFormatter={axisFormatter(range)}
              />
              <Tooltip
                contentStyle={{
                  background: colors.bgRaised,
                  border: `1px solid ${colors.border}`,
                  borderRadius: 4,
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
