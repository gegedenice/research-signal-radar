# Research Signal Radar — UI

Static React + TypeScript + Vite app (specs/06). It reads the bundle written by `radar export`
and never recomputes a statistic, a label or a rank.

```bash
# from the repository root: produce the data bundle (ui/public/data/, git-ignored)
uv run radar export

cd ui
npm install
npm run dev      # http://localhost:5173
npm test         # vitest (loader, feed selector, highlight mask, URL hash)
npm run build    # type check + production build in ui/dist/
```

- Map: deck.gl, 2-D (orthographic) or 3-D (orbit) toggle in the map corner; colour by cluster trend,
  region or abstract presence. Time bar: ▶ / Space plays, ← → steps, window or cumulative.
- Feed: ↑ ↓ to move, Enter to select, Esc to clear. Hover a card to preview its works on the map.
- The URL hash (`#year=…&signal=…&dim=3d…`) restores the view after a reload.
