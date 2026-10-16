# OpenAlex Users Meeting 2026 — talk proposal

**Title:** Research Signal Radar: an OSINT-style situation room for research output on OpenAlex

**Format:** 10-minute talk (work in progress)

**Affiliation:** _[à compléter — p. ex. SmartBibl.IA Solutions]_

## Abstract (~250 words)

Most discovery and bibliometric tools answer static questions (what exists, who publishes most, what is most cite) but they are far weaker at signal detection (strong and weak) alike what has just changed, whether that change is unusual,  whether several independent cues converge, and why it deserves attention now.

Rather than another article-search engine or a descriptive bibliometric dashboard, Research Signal Radar (RSR) is a strategic-intelligence platform for academic research that transposes the situation-awareness / OSINT loop to research output following one conceptual chain:
> Universe (a research ecosystem) → Baseline → Sweep → Observation → Delta → Candidate signal → Confirmed signal → Drill-down
You define a research ecosystem (for example an institution's portfolio), harvest and compute reference metadata from OpenAlex, learn what is normal within it through deterministic detectors with explicit confidence rules, surface silent trends and unusual changes, rank the detected signals, and jump straight to the evidence.

Three detectors are already implemented as an offline Python pipeline: Topic Momentum, Citation Acceleration (corroborated with OpenCitations data), and Actor & Collaboration Novelty.
We'll demo the working instrument on real Mines Paris–PSL data and speak candidly about the hard parts (topic granularity and small-sample noise, retrospective reconstruction from current snapshots) and about where it can go: reading an institution's strategic trajectory, spotting trends before they surface in standard bibliometrics, or exposing the processed data through an API and MCP for automation and LLM integration.