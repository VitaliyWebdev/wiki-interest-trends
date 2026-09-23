# Report design: what the PDF shows, and why

**Files:** `skills/wiki-interest-trends/scripts/report.py` (layout),
`scripts/wikitrends/chart.py` (the chart), `scripts/wikitrends/theme.py`
(shared colors), `scripts/wikitrends/i18n.py` (dates and numbers)
**Tests:** `tests/test_report.py`, `tests/test_chart.py`, `tests/test_i18n.py`

The first version of the PDF was correct but read like a debug dump: a
small blurry chart whose legend covered the data, a grey-grid table, and
half an empty page. This is the redesign, and the reasoning behind each
piece, so a later change doesn't undo one by accident.

## Layout, top to bottom

Most important first, because a stakeholder may read only the top third
(the executive-dashboard convention: headline numbers across the top,
everything below explains them).

1. **Header.** A small blue overline naming the product, then the heading:
   `--title`, else the user's `--question`, else a generic title. A long
   question steps down from 18 pt / 2 lines to 14 pt / 3 lines before
   anything is cut. Then the period and editions ("Sep 2024 – Aug 2026 ·
   Editions: en, uk"), taken from the data itself, not the query. The
   generation time is in the footer only.
2. **Conclusion callout.** The agent's `--summary` in a tinted box, up to
   six lines. The one thing on the page the script didn't compute.
3. **KPI cards.** One per series (first three) plus an overall trust card.
   Each series card has a big YoY number, what it compares ("last 12
   months vs the previous 12"), and average views. The trust card shows the
   lowest level across series, or "4 of 5 checks passed" for one series.
4. **Chart.** Vector, full width. See below.
5. **Details table.** One row per series, with a sparkline column. Not-found
   series get their own row ("no article in this edition"). A missing
   edition is a finding, and it used to be hidden in a "... N more" count.
6. **Why this trust level.** Reasons in two balanced columns, concerns (`!`)
   before strengths (`✓`). With several series, a reason every series
   shares is listed once under "All series".
7. **How to read this.** Four fixed method notes, drawn only if they fit
   whole (see "Priorities when space runs out").
8. **Footer.** Data source and generation time.

## Color carries identity, so there's no legend

`theme.SERIES_COLORS` is the Okabe-Ito palette (safe under every common
color-vision deficiency; its pale yellow is left out). Series *i* is the
same color on its chart line, its card dot, and its table sparkline.
That's what lets the chart drop the legend, which used to sit on top of
the peak markers (task `task_69806a56`, now resolved here). Lines are
labeled at their right ends instead (Knaflic / Tufte "direct labeling").

Because colors must never repeat, the chart and the table stop at
`len(SERIES_COLORS)` series (`MAX_TABLE_ROWS`); the rest are counted in
"... N more in analysis.json". An earlier cap of 8 with a 7-color palette
made the 8th line the same blue as the 1st. The stress test found it.

Direction colors (`UP` green, `DOWN` red) are never the only cue: every
colored number also has its sign and an arrow. And a YoY number is only
colored when Mann-Kendall calls the trend significant *and* it agrees with
the sign (`_direction_style`). A −3% that the test calls "no trend" stays
grey instead of reading as a decline.

## The chart

- **Vector, not PNG.** reportlab can only place raster images, so the chart
  used to be a 150 dpi PNG: blurry when zoomed, and its text invisible to
  anything reading the PDF. Now `render_chart()` writes a PDF, and
  `report.py` stamps that page onto the report with pypdf
  (`merge_transformed_page`). The chart stays sharp at any zoom, and its
  text is real text. That also made the chart testable: `test_chart.py`
  renders to PDF and reads back what was actually drawn.
- **1:1 size.** `FIGSIZE` is 180 mm wide, the page's content width, so the
  chart's 8 pt text really is 8 pt, the same as the table's. The font is
  the same DejaVu Sans. `FIGURE_PAD_PT` is shifted out past the margin so
  the chart title lines up with the rest of the page.
- **One series: views per million. Several: an index.** Two editions can
  differ 10x in views per million. On a shared axis the smaller one
  flattens into the baseline and its trend disappears (en vs uk astronomy
  did exactly that). With several series each is rebased to 100 = its own
  average, and the subtitle says so. The y-axis starts at 0 either way, so
  a decline isn't exaggerated.
- **The YoY window is shaded.** The last 12 months get a light band,
  because that's what the headline YoY number compares against the 12
  before. Only for monthly data with 24+ points; daily data has no YoY to
  explain. The band's caption sits above the plot area, where no line can
  run into it.
- **Peaks are marked; their labels never collide.** Each series' highest
  point gets a hollow marker and "peak · Jan 2025". `_drop_colliding()`
  keeps a label only if it doesn't overlap one already kept (highest peak
  first); the marker always stays.
- **Line-end labels are spread, with leaders.** `_spread()` pushes crowded
  labels apart by at least one line height. A label that had to move gets
  a thin leader line from its left edge (`relpos=(0, 0.5)`), so the line
  stays in the gap instead of cutting through the neighbouring labels, as
  it did at first.
- **Localized dates.** Month names come from `i18n.MONTHS_SHORT` (CLDR
  abbreviations), not `strftime("%b")`, which follows the process locale and
  is English everywhere these scripts run. The year shows on the first tick
  and on each January, and labels are never rotated.

## Priorities when space runs out

Everything is on one page (see `report-pdf.md` for why that's structural),
so something has to give when there's a lot of content. In order:

- The conclusion is cut at six lines, the heading at three.
- Series cards stop at three; the table has every row up to the palette cap.
- Card text picks the first phrasing that fits whole (`_first_that_fits`),
  "last 12 months vs the previous 12" → "vs the previous 12 months".
  A shorter wording reads better than a longer one cut mid-word
  ("decre…"), which is what 4-across cards produced at first.
- Trust reasons get all the remaining height. If they still don't fit, the
  last line that would fit becomes "… the rest is in analysis.json". A
  report that silently dropped reasons would look more certain than it is.
  The whole section is skipped if not even two lines fit. The trust card
  still shows the level, and nothing is ever drawn into the footer (a real
  bug with nine series; `test_a_crowded_page_never_draws_into_the_footer`
  checks the actual text positions).
- The method notes are the same text on every report, so they're the first
  thing dropped, and only whole.

## Things that only showed up by rendering

Unit tests passed through all of these; each was found by rendering a real
analysis to PNG (`qlmanage -t -s 1600`) and looking at it:

- **A path-effect halo turns chart text into outlines in PDF output.** The
  white halo behind peak labels made them unsearchable, and the tests
  checking them fail. `_annotate()` now draws the halo as a separate white
  copy *under* the real text.
- **The shading landed on the wrong half.** `axvspan(date, float_xlim)`
  mixed a date with a raw axis float; both ends are dates now.
- **Tick labels and long line-end labels were clipped** at the image edge.
  `_fit_layout()` now lays out once, measures what sticks out, and
  corrects by exactly that.
- **Daily data** got a "last 12 months" band, a "Monthly views" subtitle and
  a "peak · Sep 2026" label. Now the band is monthly-only, the subtitle
  doesn't name a granularity, and the peak and header period name days.

## Trust reasons: `concern` flag and `p<0.001`

To mark reasons ✓ / !, `analysis.json`'s `reason_codes[]` now carries
`"concern": true|false`, set by `assess_trust()` itself. The report doesn't
re-derive which codes count against the level (see `stats-and-trust.md`).
An older `analysis.json` without the flag still renders, with neutral `•`
markers. A strong trend's p-value used to print as "p=0.000", which reads
as "impossible"; it's "p<0.001" now.

## Considered, not done

- **A different font.** Inter or IBM Plex would look more modern than
  DejaVu Sans, but would mean downloading and shipping new font files.
  DejaVu is already bundled (it's matplotlib's own), covers Cyrillic, and
  keeps the chart and page in one typeface. It would be a small change if
  wanted.
- **svglib for vector charts.** It works, but pulls in lxml; pypdf is pure
  Python and was already a test dependency.
- **Small multiples** (one panel per series). They're better for many series
  of very different shapes, but the index handles the common 2-4 series
  case on one comparable axis, and the sparklines already give each series
  its own-scale view.

## Research this is based on

- KPI cards first, one comparison each, units and date range always shown:
  [Tabular Editor — KPI card best practices](https://tabulareditor.com/blog/kpi-card-best-practices-dashboard-design).
- Index vs small multiples vs log scale for series of different
  magnitude: [Datawrapper — small multiple line charts](https://www.datawrapper.de/blog/what-to-consider-when-creating-small-multiple-line-charts),
  [Flourish — log vs linear](https://flourish.studio/blog/log-linear-scales/).
- Direct labels instead of legends, and repelling overlapping ones:
  [Don't Use This Code — lose the legend](https://www.dontusethiscode.com/blog/2023-05-03-lose_the_legend.html),
  [Spectalizer — optimized direct labeling](https://www.spectalizer.com/blog/2025-06-direct-line-labeling/).
- Sparklines, "word-sized graphics" with no axes or frames:
  [Tufte — sparkline theory and practice](https://www.edwardtufte.com/notebook/sparkline-theory-and-practice-edward-tufte/).
- Okabe-Ito palette:
  [Okabe-Ito hex reference](https://conceptviz.app/blog/okabe-ito-palette-hex-codes-complete-reference).
