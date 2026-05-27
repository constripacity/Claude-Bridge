# Terminal UI — Design Reference

React/JSX mockups of the `python tui.py` terminal companion. These are
non-runtime visual specs — the live implementation lives in `tui.py` at the
repo root and uses [Textual](https://textual.textualize.io).

## View the canvas

Open `index.html` directly in a browser, or serve this folder:

```bash
python -m http.server -d docs/design/terminal 8080
```

Then visit `http://localhost:8080`.

## Layouts

| File | What it shows |
|------|---------------|
| `tui-full.jsx`       | 220×50 desktop layout — sidebar + feed + inspector + send + status |
| `tui-variants.jsx`   | 120×35 (laptop) and 80×24 (tmux pane) responsive variants |
| `tui-states.jsx`     | mode variants — filter, send, offline, error |
| `tui-startup.jsx`    | 4-frame boot sequence |
| `tui-components.jsx` | individual re-usable parts |
| `tui-core.jsx`       | palette, helpers, sample data |
| `shared.jsx`         | shared design tokens |

## Sister docs

The web dashboard's design mockups have already been implemented in `web/` —
this folder is the TUI's equivalent reference.
