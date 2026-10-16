# Research Signal Radar

Read specs/01_overview-and-decisions.md before any change. The spec for the current step is
named in the request. Specs are the source of truth; if code and spec disagree, ask.

Rules
- Keep it simple. This is a prototype. Do not add stages, scores, confidence layers, schemas
  or abstractions that the specs do not ask for. If something seems missing, propose it in one
  sentence and wait.
- One statistical engine (src/radar/engine.py). Detectors only build counts and denominators.
- No LLM anywhere. Embeddings only for the semantic map.
- The UI never recomputes statistics, labels or ranks.
- Secrets only from environment variables (.env, git-ignored). Never log keys or URLs with keys.
- Tests: pytest (Python), vitest (UI). No network in tests.
- Python ≥ 3.11, managed with uv. New dependencies need a one-line justification in the PR.

Commands
- uv run radar sweep | detect | embed | map | export
- uv run pytest
- cd ui && npm run dev | npm run build | npm test
