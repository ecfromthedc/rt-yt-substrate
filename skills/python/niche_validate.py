#!/usr/bin/env python3
"""
/niche-validate — score a candidate niche against the gate before you commit a channel.

Combines a live competitive probe (yt-dlp search) with an RPM reference table and
local-Ollama reasoning to produce a PASS / CAUTION / KILL verdict on a niche:
RPM band, saturation, demonetization risk, evergreen-vs-fad. The final human step is
always a manual Google Trends check — this skill gets you 90% of the way and tells you
exactly what to verify.

Per CLAUDE.md: the reasoning runs on local Ollama; the operator does the final Trends call.

Usage:
  python3 niche_validate.py --niche "forgotten ancient empires" --lane history
  python3 niche_validate.py --niche "self-hosted homelab tutorials"
"""
import argparse, json, os, re, subprocess, sys, urllib.request, datetime

OLLAMA = "http://localhost:11434/api/generate"
MODEL = os.environ.get("NICHE_MODEL", "qwen2.5:7b")

# RPM reference bands (US/UK, 2026) — the gate floor is $7.
RPM_TABLE = {
    "finance": "15-30", "investing": "15-30", "business": "10-15", "saas": "15-25",
    "ai": "10-18", "dev": "10-18", "tech": "12-20", "legal": "12-18", "real estate": "15-25",
    "medical": "12-20", "history": "7-13", "aviation": "7-13", "true crime": "8-12",
    "meditation": "1-3", "sleep": "1-3", "gaming": "2-4", "kids": "1-3", "entertainment": "2-5",
}

def rpm_hint(niche):
    n = niche.lower()
    hits = [f"{k}: ${v}" for k, v in RPM_TABLE.items() if k in n]
    return "; ".join(hits) if hits else "(no direct table match — Ollama will estimate)"

def run(cmd, timeout=90):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        class R: returncode = 1; stdout = ""; stderr = str(e)
        return R()

def probe_saturation(niche, n=20):
    """Flat yt-dlp search → the competitive surface (titles + channels)."""
    r = run(["yt-dlp", f"ytsearch{n}:{niche}", "--flat-playlist", "--dump-json",
             "--no-warnings"], timeout=120)
    rows, channels = [], set()
    for line in r.stdout.splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        ch = e.get("channel") or e.get("uploader") or "?"
        channels.add(ch)
        rows.append({"title": e.get("title") or "", "channel": ch, "views": e.get("view_count") or 0})
    return rows, channels

def ollama(prompt, num_predict=900):
    body = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "options": {"temperature": 0.2, "num_predict": num_predict}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=200) as resp:
            return json.loads(resp.read())["response"].strip()
    except Exception as e:
        return f"_(Ollama unavailable: {e}. Start it with `ollama serve`. RPM/saturation data above still valid.)_"

def assess(niche, lane, rpm, rows, channels):
    surface = "\n".join(f"- [{r['channel']}] {r['title'][:70]}" for r in rows[:18]) or "(no search results returned)"
    p = (
        f"You are a YouTube niche analyst applying Rising Tides' gate: RPM >= $7, evergreen OR rising demand, "
        f"and a real gap (not oversaturated). Niche under evaluation: \"{niche}\"" + (f" (lane: {lane})" if lane else "") + ".\n\n"
        f"RPM reference for this niche: {rpm}\n\n"
        f"Live competitive surface (top YouTube results — {len(channels)} distinct channels):\n{surface}\n\n"
        f"Produce a tight scorecard, no preamble:\n"
        f"1. **RPM verdict** — band + does it clear the $7 floor?\n"
        f"2. **Saturation** — read the surface: is this dominated by a few giants (hard to break in), wide-open, or a healthy gap? One call: LOW / MEDIUM / HIGH saturation.\n"
        f"3. **Demonetization risk** — any reused-content / AI-slop / sensitive-topic / inauthentic-content risk (YouTube's 2025+ rules)? LOW/MED/HIGH + why.\n"
        f"4. **Evergreen vs fad** — will this still pull views in 2 years, or does it decay? EVERGREEN / RISING / FAD.\n"
        f"5. **VERDICT** — one of PASS / CAUTION / KILL, with a one-sentence reason.\n"
        f"6. **The angle** — if PASS/CAUTION, the single most defensible sub-angle to attack first."
    )
    return ollama(p)

def write_card(niche, lane, rpm, channels, body, out):
    today = os.environ.get("NICHE_DATE", datetime.date.today().isoformat())
    verdict = "UNKNOWN"
    m = re.search(r"\b(PASS|CAUTION|KILL)\b", body)
    if m: verdict = m.group(1)
    slug = re.sub(r"[^a-z0-9]+", "-", niche.lower()).strip("-")[:50]
    path = os.path.join(out, f"niche-validate-{slug}.md")
    os.makedirs(out, exist_ok=True)
    md = f"""---
type: niche-validation
niche: "{niche}"
lane: {lane or "unassigned"}
date: {today}
verdict: {verdict}
distinct_channels_in_surface: {len(channels)}
rpm_reference: "{rpm}"
status: machine pre-screen — operator must finish with a manual Google Trends check
---

# Niche Validation — "{niche}"

**Verdict: {verdict}**

{body}

---
## ⚠️ The human step you still owe (non-negotiable)
Open **Google Trends** → search "{niche}" → filter **United States / Past 12 months / YouTube Search**.
- Rising or stable → keep. Declining → kill (unless truly evergreen).
- Compare against 2-3 adjacent angles side by side; attack the one trending up.

_"AI is a tool, not a replacement for your brain. Verify the data." — the whole point of the gate._

Regenerate: `python3 ~/Projects/active/rt-yt-skills/niche_validate.py --niche "{niche}"{f' --lane {lane}' if lane else ''}`
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    return path, verdict

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--niche", required=True)
    ap.add_argument("--lane", default="")
    ap.add_argument("--out", default=os.environ.get("RT_YT_OUT_DIR", "./out"))
    a = ap.parse_args()
    rpm = rpm_hint(a.niche)
    print(f"[niche-validate] probing competitive surface for '{a.niche}' …", file=sys.stderr)
    rows, channels = probe_saturation(a.niche)
    if not rows:
        print("[niche-validate] WARN: yt-dlp returned no results (rate limit or odd query) — Ollama assessing on RPM only.", file=sys.stderr)
    body = assess(a.niche, a.lane, rpm, rows, channels)
    path, verdict = write_card(a.niche, a.lane, rpm, channels, body, a.out)
    print(f"[niche-validate] verdict: {verdict}", file=sys.stderr)
    print(path)

if __name__ == "__main__":
    main()
