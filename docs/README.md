# RT YouTube Long-Form — Workflow Map

Single source of truth for the long-form pipeline.

## Files

- **`workflow.yaml`** — schema-driven definition. Stages, tools, owners, data flows, costs. Edit this, everything else regenerates.
- **`workflow-map.html`** — human-readable view. Mermaid data-flow diagram + stage cards + tool stack table. Open in a browser.
- **`obsidian-canvas-sync.sh`** — generates `Rising Tides OS/YouTube Long-Form/Workflow Map.canvas` from `workflow.yaml` for Obsidian users.

## Edit flow (any agent — Glitch's, Jay's, Smaths', Eric's)

1. Branch off `main`.
2. Edit `workflow.yaml` only — never edit the HTML directly, it regenerates.
3. Open a PR to `rt-yt-substrate`.
4. CI lints schema + Mermaid build.
5. Substrate owner reviews + merges.
6. HTML + Canvas auto-regen on merge.
7. Channel announcement posts to `#5d-chess-with-the-universe`.

## Why YAML, not Notion?

Notion is the human-facing project tracker (Stage Index, per-video kanban). The workflow *map* is upstream of that — it defines what the pipeline IS, who owns each stage, what tools come into play where. Living in the repo means every agent can read it, propose changes, and the audit trail is git, not Slack threads.
