# Frontend — Component Summary

Status: **complete**. 58 unit tests, eslint and tsc clean, static export builds to 111 kB first
load.

## Structure

```
frontend/
├── app/               layout, page (the single dashboard), globals.css
├── lib/
│   ├── theme.ts       design tokens — the one source for Tailwind and canvas charts
│   ├── types.ts       wire types mirroring API_CONTRACT.md
│   ├── format.ts      every displayed number goes through here
│   ├── api/           fetch wrapper that understands the error envelope
│   └── stream/        price store + the single EventSource hook
├── store/             portfolio, watchlist, chat
└── components/        layout, watchlist, chart, portfolio, trade, chat, ui
```

## The decisions that shaped it

**State is split by update frequency, not by feature.** Live prices sit in their own store, so a
2Hz tick cannot notify the portfolio, watchlist, or chat stores. A React context would have
re-rendered every consumer twice a second, because context has no selector.

**Three charting tools, deliberately.** Sparklines are hand-drawn SVG polylines — 25 chart
instances would each carry observers and a render loop for a line with no axes. The main chart is
lightweight-charts, fed from a store subscription outside React's render cycle, because it is the
one genuinely hot path. The P&L chart and heatmap are Recharts, where updates arrive every 30
seconds and declarative SVG beats canvas throughput.

**The flash costs no extra render.** The class is derived during the render the price change
already causes, and a `key` tied to the timestamp restarts the CSS animation. `useState` plus
`setTimeout` would double the render count per row per tick and leave overlapping timers.

**Colour is never the only encoding.** Every P&L figure carries a glyph and an explicit sign,
heatmap cells always draw a signed percentage, and the connection dot is paired with a text label.

**`daily_change_percent`, never `change_percent`.** The latter is tick-over-tick and sits near
zero. Confusing them is the most likely integration bug in this app, so the store normalizes at
the parse boundary and a test pins the behaviour.

## Bugs found by running it, not by reading it

- The main chart drew nothing: the history buffer ticks twice a second while the series is keyed by
  whole seconds, so seeding handed it duplicate timestamps, which it rejects outright.
- The heatmap drew every label twice: Recharts invokes the content renderer for the root node as
  well as the leaves.
- The P&L axis collapsed every tick to the same value when the portfolio moved only a few dollars.
- The header claimed "Live" over frozen prices when the network dropped, because EventSource does
  not fire `onerror` on a stalled connection. A staleness watchdog now reports it.

## Where to look first

| Question | File |
|---|---|
| What shape is the data? | `lib/types.ts`, `planning/API_CONTRACT.md` |
| How do prices reach a component? | `lib/stream/priceStore.ts` |
| Why is this colour used? | `lib/theme.ts` |
| How does the chart stay live? | `components/chart/MainChart.tsx` |
