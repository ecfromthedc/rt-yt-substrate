# rt-yt-substrate

Substrate for the Rising Tides YouTube long-form growth lab.

This repo owns:

- **Postgres schema** for `rt-yt-automations` (Railway, isolated project)
- **Rust services**: Notion↔Postgres sync adapter, Neo4j HTTP wrapper, Gap-Finder daemon, cron jobs
- **Python skills layer**: `/teardown`, `/topic-loop`, `/winner-log`, `/niche-validate`, `/script-bible`, `/format-extract`, `/lab-query`
- **Stage SOPs**: 10 stage runbooks mirroring the Notion `Stage SOPs` section
- **Docs**: schema design notes, lock patterns, agent contracts

## Topology

| Substrate | Role | Access |
|---|---|---|
| **Postgres `rt-yt-automations`** (Railway, isolated) | Authoritative pipeline state + event log | All four Claudes via `YT_AUTOMATIONS_DATABASE_URL` |
| **Notion `YouTube Automations`** | Human view, mirrored from Postgres | Humans + bots via Notion API |
| **`rt-yt-knowledge`** (sister repo) | Channel teardowns, format library, prompt evolutions, tool evals | Cloned by every Claude that needs the corpus |
| **`youtube-growth-playbook`** (public reference) | 5-step methodology, role contracts, prompt library | Public clone |
| **Neo4j (over Cloudflare tunnel from Eric's Mac)** | Graph + vector embeddings for retrieval | HTTP wrapper exposes read endpoints |

Postgres is the source of truth. Notion is allowed to be eventually consistent. If the two disagree, Postgres wins.

## Repo layout

```
rt-yt-substrate/
├── migrations/         # Postgres schema migrations (numbered)
├── substrate/
│   └── rust/           # sync adapter, neo4j wrapper, gap-finder, crons
├── skills/
│   └── python/         # /teardown, /topic-loop, /winner-log, etc.
├── sops/               # 10 stage SOPs (mirror of Notion Stage SOPs)
├── docs/               # design notes, lock patterns, agent contracts
└── .env.example        # env var contract (no real secrets)
```

## State machine

Glitch is the sole gate owner across all 10 stages. Jay and Eric can contribute creative input via the `creative_input_requested_from` field, but the pipeline does not wait on them and they cannot block.

Stage transitions are gated by the `allowed_next_stage` rules. Any bot writing through the sync adapter must hold a `SELECT ... FOR UPDATE` lock on the row before mutating. See `docs/lock-patterns.md` (added in schema PR).

## Local dev

```bash
# Source the env (held outside the repo)
source ~/.cortextos/default/rt-yt-automations.env

# Apply migrations
psql "$YT_AUTOMATIONS_DATABASE_URL" -f migrations/0001_initial_schema.sql

# Skills
cd skills/python && uv sync
uv run teardown --url https://www.youtube.com/watch?v=...
```

## Status

- [x] Repos created (`rt-yt-substrate`, `rt-yt-knowledge`)
- [x] Railway Postgres `rt-yt-automations` provisioned (isolated project)
- [ ] Schema applied + PR'd
- [ ] Sync adapter scaffold (Rust)
- [ ] `/teardown` skill (Python)
- [ ] Neo4j HTTP wrapper (Rust, over Cloudflare tunnel)
- [ ] Gap-Finder daemon (Rust)

Tracked in #5d-chess-with-the-universe.
