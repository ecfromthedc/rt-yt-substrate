# Python skills layer

Operator + swarm skills for the rt-yt-automations pipeline.

- **teardown.py** (v1, working) — competitor channel teardown: yt-dlp outlier pull (caption fast-path, no whisper) + local Ollama title/hook pattern extraction -> corpus teardown doc. `python3 teardown.py --channel @Handle --lane history`
- **topic_loop.py** (v1, working) — validated topic queue per lane: reads Script Bible + teardowns, Ollama-generates N topics on the proven formulas, avoids competitor topics. `python3 topic_loop.py --lane history --n 12`
- niche-validate, script-bible, winner-log, format-extract, lab-query — planned.

Local-LLM offload (CLAUDE.md): bulk extraction on Ollama; synthesis by Claude/operator.
