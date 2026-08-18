# Frontend — Component Summary

Status: **complete**. 107 unit tests, 20 E2E, eslint and tsc clean, static export builds to
116 kB first load and ships no font files.

## Structure

```
frontend/
├── app/               layout, page (the single dashboard), globals.css
├── lib/
│   ├── theme.ts       design tokens — two palettes, the one source for Tailwind and charts
│   ├── useTheme.ts    the current appearance, for everything CSS cannot reach
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

**The palette forks, rather than the sources.** Two appearances mean Tailwind and the charts can
no longer share one static object: Tailwind resolves at build time, the charts need a concrete
colour at draw time. `theme.ts` stays the only file with a colour literal in it and emits both —
a `:root` stylesheet of "R G B" channel triples for Tailwind, and a plain object for the charts.
The triples rather than hexes are what keep `bg-blue/15` working.

**Each system colour splits three ways.** A colour picked to look right cannot also carry text:
white on systemGreen is 2.2:1, systemGreen on white is 1.9:1. So `up` is the vivid one for chart
strokes and tints, `upFill` is darkened until a white button label clears 4.5:1, and `upText` is
darkened until it clears 4.5:1 as small text. `__tests__/lib/theme.test.ts` holds all of it to
the line in both appearances — it caught nine failures the moment it was written, including two
the eToro build had shipped.

**The appearance is decided before React exists.** A blocking script in `<head>` stamps
`data-theme` from storage or the OS. The store adopts that after mount rather than resolving it
during render, because the pages are prerendered and deciding earlier would make the client's
first markup disagree with the exported HTML.

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
- The price flash, ported at one fixed alpha, turned the whole price column into solid badges in
  dark mode — the tint that is a shimmer on white is a fill on black. Its strength is a palette
  token now.
- The sidebar labels are `display:none` below `lg`, which takes them out of the accessibility
  tree as well as the layout, leaving four unnamed buttons on a phone.

## Where to look first

| Question | File |
|---|---|
| What shape is the data? | `lib/types.ts`, `planning/API_CONTRACT.md` |
| How do prices reach a component? | `lib/stream/priceStore.ts` |
| Why is this colour used? | `lib/theme.ts` |
| Which appearance am I in? | `lib/useTheme.ts` |
| How does the chart stay live? | `components/chart/MainChart.tsx` |
