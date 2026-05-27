# Design canvas

This directory archives the original Claude Design artboards used to design
the dashboard. They render via [Babel-standalone] in `index.html` and are kept
here purely as reference — they are **not** the live dashboard.

| File | Artboard |
|------|----------|
| `dashboard-desktop.jsx` | Live monitor UI · 1280 × 800 |
| `dashboard-mobile.jsx`  | Live monitor UI · 390 × 844 |
| `landing-hero.jsx`      | README hero / marketing page |
| `tokens-sheet.jsx`      | Design tokens & components |
| `logo-sheet.jsx`        | Logo & wordmark |
| `shared.jsx`            | Icons, sender pills, JSON highlighter, brand mark |
| `design-canvas.jsx`     | The canvas/artboard framework |

The **live** dashboard lives in [`/web`](../../web/) and is served by
`server.py` at `http://localhost:8765/`. It reuses the same visual language
but is wired to real `/api/state`, `/api/messages`, `/api/send`, and
`/api/clear` endpoints.

To preview these artboards locally, open `index.html` in any browser — no
build step needed.

[Babel-standalone]: https://babeljs.io/docs/babel-standalone
