#!/usr/bin/env python3
"""
/teardown — competitor channel teardown (caption fast-path, Ollama-offloaded).

Pulls a competitor channel's outlier videos via yt-dlp, grabs captions for the
top performers (no whisper needed), and uses local Ollama to extract title +
hook patterns. Writes a teardown doc in the rt-yt-knowledge corpus format.

Per CLAUDE.md: bulk extraction runs on local Ollama; Claude handles synthesis/curation.

Usage:
  python3 teardown.py --channel @VoicesofthePast --lane history
  python3 teardown.py --channel https://www.youtube.com/@Fireship --lane ai-dev --top 12
"""
import argparse, json, os, re, subprocess, sys, urllib.request, datetime

OLLAMA = "http://localhost:11434/api/generate"
MODEL = os.environ.get("TEARDOWN_MODEL", "qwen2.5:7b")

def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def channel_url(handle):
    h = handle.strip()
    if h.startswith("http"):
        base = h.rstrip("/")
    else:
        if not h.startswith("@"):
            h = "@" + h
        base = f"https://www.youtube.com/{h}"
    return base + "/videos"

def fetch_videos(handle, limit=25):
    """Per-video metadata for recent uploads (full extract so view_count is populated)."""
    url = channel_url(handle)
    r = run(["yt-dlp", "--dump-json", "--playlist-end", str(limit),
             "--ignore-errors", "--no-warnings", url], timeout=300)
    vids = []
    for line in r.stdout.splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        vids.append({
            "id": e.get("id"),
            "title": e.get("title") or "",
            "views": e.get("view_count") or 0,
            "duration": e.get("duration") or 0,
            "url": e.get("url") or f"https://youtu.be/{e.get('id')}",
        })
    return [v for v in vids if v["id"] and v["title"]]

def fetch_hook(video_id, max_words=140):
    """Grab auto/manual EN captions, return first ~max_words (the hook). Fast-path, no whisper."""
    out = f"/tmp/td-{video_id}"
    run(["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
         "--sub-langs", "en.*,en", "--sub-format", "vtt", "-o", out,
         f"https://youtu.be/{video_id}"], timeout=90)
    # find the produced sub file
    sub = None
    for f in os.listdir("/tmp"):
        if f.startswith(f"td-{video_id}") and f.endswith(".vtt"):
            sub = os.path.join("/tmp", f); break
    if not sub:
        return None
    text = []
    seen = set()
    with open(sub, encoding="utf-8", errors="ignore") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln or "-->" in ln or ln.startswith(("WEBVTT", "Kind:", "Language:")):
                continue
            ln = re.sub(r"<[^>]+>", "", ln)            # strip inline timing tags
            if ln and ln not in seen:
                seen.add(ln); text.append(ln)
            if sum(len(t.split()) for t in text) > max_words:
                break
    try: os.remove(sub)
    except Exception: pass
    return " ".join(text)[:1200] if text else None

def ollama(prompt, num_predict=700):
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.2, "num_predict": num_predict}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read())["response"].strip()
    except Exception as e:
        sys.stderr.write(
            f"\n[!] Ollama not reachable ({e}).\n"
            f"    Fix: run `ollama serve` in a terminal, then `ollama pull {MODEL}` if the model is missing. Then retry.\n\n")
        sys.exit(2)

def analyze_titles(top):
    lines = "\n".join(f"- {v['views']:>10,} views | {v['title']}" for v in top)
    p = (f"You are a YouTube packaging analyst. Below are a channel's top videos by views.\n{lines}\n\n"
         "Extract the WINNING TITLE PATTERNS. Be concrete and specific to these titles. Output:\n"
         "1. Recurring title structures (the reusable formula, with a template like '<X> that <Y>')\n"
         "2. Power words / emotional triggers they repeat\n"
         "3. What the highest-view titles do that the lower ones don't\n"
         "4. The curiosity-gap mechanism they use\n"
         "Keep it tight — bullets, no preamble.")
    return ollama(p)

def analyze_hooks(hooks):
    blob = "\n\n".join(f"[{i+1}] {h}" for i, h in enumerate(hooks) if h)
    if not blob.strip():
        return "_No captions available for top videos (likely none published or region-blocked)._"
    p = ("You are a retention analyst. Below are the opening ~60 seconds (transcript) of top videos.\n\n"
         f"{blob}\n\n"
         "Extract the HOOK PATTERN these openings share. Output:\n"
         "1. What they ALL do in the first 1-2 sentences\n"
         "2. How they create an open loop / stakes\n"
         "3. The pacing / structure of the cold open\n"
         "Concrete bullets only, no preamble.")
    return ollama(p)

def write_doc(handle, lane, vids, top, title_pat, hook_pat, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", handle.lstrip("@").lower()).strip("-")
    path = os.path.join(out_dir, f"{slug}.md")
    today = os.environ.get("TEARDOWN_DATE", datetime.date.today().isoformat())
    avg = (sum(v["views"] for v in vids) / max(1, len(vids))) or 1
    top_avg = (sum(v["views"] for v in top) / max(1, len(top))) or 1
    rows = "\n".join(f"| {v['title'][:70]} | {v['views']:,} | {int(v['duration']//60)}m | "
                     f"{(v['views']/avg):.1f}x |" for v in top)
    md = f"""---
type: teardown
lane: {lane}
channel: {handle}
torn_down_by: /teardown swarm (ollama:{MODEL})
date: {today}
videos_sampled: {len(vids)}
---

# Teardown — {handle}

## 1. The numbers
- Videos sampled: **{len(vids)}** (recent uploads)
- Channel avg views: **{avg:,.0f}** · Top-10 avg: **{top_avg:,.0f}** ({top_avg/max(1,avg):.1f}x the baseline)
- Outlier signal: the top videos pull **{top[0]['views']/max(1,avg):.1f}x** the channel average — the power law is live on this channel.

## 2. Top videos (the outliers — where the money is)
| Title | Views | Len | vs avg |
|---|---|---|---|
{rows}

## 3. Title patterns (Ollama-extracted)
{title_pat}

## 4. Hook patterns (opening ~60s of top videos)
{hook_pat}

## 5. The steal list
- **Copy:** the title formula + cold-open structure above.
- **Beat them on:** packaging contrast + upload cadence.
- _Operator: fill after first 3 shipped videos in this cluster._

> Auto-generated by `/teardown` (caption fast-path + local Ollama). Review, then promote to `rt-yt-knowledge/lanes/{lane}/teardowns/`.
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--lane", required=True)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--hooks", type=int, default=3)
    ap.add_argument("--out", default=os.environ.get("RT_YT_OUT_DIR", "./out"))
    a = ap.parse_args()
    print(f"[teardown] fetching {a.channel} …", file=sys.stderr)
    vids = fetch_videos(a.channel)
    if not vids:
        print("ERROR: no videos found (check handle).", file=sys.stderr); sys.exit(1)
    top = sorted(vids, key=lambda v: v["views"], reverse=True)[:a.top]
    print(f"[teardown] {len(vids)} videos, analyzing top {len(top)} …", file=sys.stderr)
    hooks = []
    for v in top[:a.hooks]:
        print(f"[teardown]   captions: {v['title'][:50]}", file=sys.stderr)
        hooks.append(fetch_hook(v["id"]))
    title_pat = analyze_titles(top)
    hook_pat = analyze_hooks(hooks)
    out_dir = os.path.join(a.out, a.lane, "teardowns")
    path = write_doc(a.channel, a.lane, vids, top, title_pat, hook_pat, out_dir)
    print(path)

if __name__ == "__main__":
    main()
