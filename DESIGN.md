# DESIGN.md — look and feel

## Identity
- Name: **GB Grid Live**. Tagline: "Use power when the grid is cleanest."
- Mood: calm, trustworthy, data-journalism quality (think Financial Times charts or Our World in Data), not a flashy dashboard.
- Own identity only. No NESO, Sheffield Solar or energy-company logos or colours.

## Colour tokens (dark default, with a light theme)
| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| `--bg` | #0E1621 | #F7F8FA | page background |
| `--surface` | #16212E | #FFFFFF | cards |
| `--text` | #E8EDF2 | #14202B | main text |
| `--text-muted` | #9AA8B6 | #5B6975 | labels, captions |
| `--accent` | #3DDC97 | #12966A | links, selected state, "clean" highlight |
| `--grid` | #26323F | #E3E7EC | chart gridlines |

Carbon intensity scale (sequential, clean → dirty), used consistently on every chart and the map:
`very low #1B9E77 · low #66C2A5 · moderate #F2C14E · high #F08A4B · very high #D1495B`
Always pair colour with the band name or value (never colour alone). Check contrast ≥ 4.5:1 for text.

Fuel colours (fixed everywhere): wind #4FB3D9, solar #F2C14E, nuclear #9B7FD1, gas #8C96A3, biomass #6FA36B, hydro #3A7CA5, imports #C9A27E, coal #4A4A4A, other #B0B0B0.

## Typography and layout
- Font: Inter (Google Fonts), fallback system-ui. Numbers use tabular figures.
- Sizes: headline number 48–64px, H1 28px, H2 20px, body 15–16px, captions 13px.
- 8px spacing grid, cards with 12px radius, 1px subtle border, no heavy shadows or gradients.
- Max content width 1200px; single column below 768px. Top navigation becomes a bottom tab bar on mobile.

## Charts (Apache ECharts)
- Chart title = the finding ("Cleanest window tomorrow: 13:00–17:00"), subtitle = what is plotted.
- Minimal gridlines, no 3D, no pie charts beyond the single generation donut.
- Forecast shown as a line with a lighter band where uncertainty is shown; "now" marked by a vertical line.
- Tooltips show the local time, value with units, and band name.
- Animations short (≤ 300ms) and respect `prefers-reduced-motion`.

## Tone of words
Plain English, short sentences, UK spelling. Explain jargon on first use (e.g. "carbon intensity: grams of CO₂ emitted per unit of electricity").
