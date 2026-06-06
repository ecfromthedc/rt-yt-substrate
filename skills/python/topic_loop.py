#!/usr/bin/env python3
"""
/topic-loop — generate a validated topic queue for a lane from its corpus.

Reads the lane's Script Bible + teardowns (the proven title formulas + the topics
competitors already used), then has local Ollama generate N fresh topic ideas that
FIT the winning formulas without copying competitor topics. Outputs a ready-to-ship
topic queue the operator can grab from.

Per CLAUDE.md: the bulk generation runs on local Ollama; the operator curates + Trends-verifies.

Usage:
  python3 topic_loop.py --lane history --n 12
"""
import argparse, json, os, re, glob, sys, urllib.request, datetime

OLLAMA = "http://localhost:11434/api/generate"
MODEL = os.environ.get("TOPIC_MODEL", "qwen2.5:7b")
SEED = os.path.expanduser(
    "~/Documents/Obsidian Vault/Rising Tides OS/Session Logs/2026-06/session-2026-06-05/yt-1mil-plan/rt-yt-knowledge-SEED")

def read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""

def ollama(prompt, num_predict=1400):
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.5, "num_predict": num_predict}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            return json.loads(resp.read())["response"].strip()
    except Exception as e:
        sys.stderr.write(
            f"\n[!] Ollama not reachable ({e}).\n"
            f"    Fix: run `ollama serve`, then `ollama pull {MODEL}` if needed. Then retry.\n\n")
        sys.exit(2)

def gather(lane):
    bible = read(os.path.join(SEED, "lanes", lane, "script-bible.md"))
    teardowns = [read(p) for p in glob.glob(os.path.join(SEED, "lanes", lane, "teardowns", "*.md"))]
    # pull competitor titles out of the teardown tables (lines with " | " and a view count)
    used = []
    for t in teardowns:
        for ln in t.splitlines():
            m = re.match(r"\|\s*(.+?)\s*\|\s*[\d,]+\s*\|", ln)
            if m and m.group(1).lower() not in ("title",):
                used.append(m.group(1))
    return bible, used

def generate(lane, n, bible, used):
    used_blob = "\n".join(f"- {t}" for t in used[:40]) or "(none parsed)"
    bible_excerpt = bible[:4000] if bible else "(no script bible found)"
    p = (
        f"You are the topic strategist for a faceless long-form YouTube channel in the '{lane}' niche.\n\n"
        f"=== THE WINNING PLAYBOOK (this lane's Script Bible) ===\n{bible_excerpt}\n\n"
        f"=== TOPICS COMPETITORS ALREADY USED (do NOT repeat these — find fresh angles) ===\n{used_blob}\n\n"
        f"Generate EXACTLY {n} NEW video topics for OUR channel. Each must:\n"
        f"- use one of the proven TITLE FORMULAS from the Script Bible\n"
        f"- open a curiosity gap (specific, stakes, an unresolved question)\n"
        f"- be evergreen or rising in interest (no fad that decays in days)\n"
        f"- NOT duplicate a competitor topic above (adjacent/fresh angle only)\n\n"
        f"Output a numbered markdown list. For EACH topic, exactly these 3 lines:\n"
        f"**<the video title, <70 chars>**\n"
        f"- Formula: <which proven formula it uses>\n"
        f"- Why it works: <the curiosity gap / why it earns the click, one sentence>\n"
        f"No preamble, no closing remarks — just the {n} topics."
    )
    return ollama(p)

def write_queue(lane, n, topics, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "topic-queue.md")
    today = os.environ.get("TOPIC_DATE", datetime.date.today().isoformat())
    md = f"""---
type: topic-queue
lane: {lane}
generated: {today}
count: {n}
source: script-bible + teardowns (Ollama:{MODEL})
status: candidates — operator must Trends-verify (US / 12mo / YouTube Search) before producing
---

# {lane} — Topic Queue

> {n} candidate topics built from the lane's proven title formulas, avoiding competitor topics.
> **Before producing:** verify each in Google Trends (US / past 12mo / YouTube Search). Keep rising + evergreen, kill declining. Then package (title + thumbnail) FIRST.

{topics}

---
_Regenerate anytime: `python3 ~/Projects/active/rt-yt-skills/topic_loop.py --lane {lane} --n {n}`_
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lane", required=True)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--out", default=None)
    ap.add_argument("--force", action="store_true", help="generate even if the lane has no Script Bible")
    a = ap.parse_args()
    bible, used = gather(a.lane)
    if not bible and not a.force:
        lanes = sorted(os.path.basename(p.rstrip("/")) for p in glob.glob(os.path.join(SEED, "lanes", "*", "")))
        sys.stderr.write(
            f"\n[!] No Script Bible for lane '{a.lane}' at {SEED}/lanes/{a.lane}/script-bible.md\n"
            f"    A topic queue without a bible is ungrounded guesswork — refusing to write junk.\n"
            f"    Available lanes: {', '.join(lanes) or '(none)'}\n"
            f"    Build a Script Bible first (run /teardown then synthesize), or pass --force to override.\n\n")
        sys.exit(2)
    if not bible:
        print(f"WARN: --force set — no bible for '{a.lane}', generating from formulas only.", file=sys.stderr)
    print(f"[topic-loop] {a.lane}: {len(used)} competitor topics parsed, generating {a.n} …", file=sys.stderr)
    topics = generate(a.lane, a.n, bible, used)
    out_dir = a.out or os.path.join(SEED, "lanes", a.lane)
    path = write_queue(a.lane, a.n, topics, out_dir)
    print(path)

if __name__ == "__main__":
    main()
