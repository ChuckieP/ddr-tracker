#!/usr/bin/env python3
"""
DDR Life4 Platinum Tracker — Remote MCP Server
Deploy to Railway for use from any Claude chat (including mobile).

Environment variables:
  DDR_API_KEY   — bearer token required on all requests (set this in Railway)
  SCORES_PATH   — where to store the scores CSV (default: /data/scores.csv)
  PORT          — set automatically by Railway
"""

import csv
import io
import json
import os
import re
import urllib.request
import uvicorn
from pathlib import Path
from starlette.responses import PlainTextResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

# Shared evaluation logic lives in tracker.py
from tracker import PLATINUM, ROMAN, ICON, AAA_SCORE, evaluate

# ── Config ───────────────────────────────────────────────────────────────────────

SCORES_FILE   = Path(os.environ.get("SCORES_PATH", "/data/scores.csv"))
PLAYLIST_FILE = Path(os.environ.get("SCORES_PATH", "/data/scores.csv")).parent / "playlist.json"
API_KEY       = os.environ.get("DDR_API_KEY", "")

# Maps 3icecream full difficulty name → standard DDR abbreviation
DIFF_ABBREV = {
    "BEGINNER":  "BEG",
    "BASIC":     "BSP",
    "DIFFICULT": "DSP",
    "EXPERT":    "ESP",
    "CHALLENGE": "CSP",
}

mcp = FastMCP("DDR Tracker")

# ── Score I/O ─────────────────────────────────────────────────────────────────────

def load_scores():
    """Load scores from stored CSV. Returns None if no file exists yet."""
    if not SCORES_FILE.exists():
        return None
    songs = []
    with open(SCORES_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            songs.append({
                "id":    row["Song ID"],
                "name":  row["Song Name"],
                "diff":  row["Difficulty"],
                "level": int(row["Rating"]),
                "score": int(row["Score"]),
                "grade": row["Grade"],
                "lamp":  row["Lamp"],
            })
    return songs


def save_scores(csv_text: str) -> int:
    """Save CSV text to disk. Returns number of rows saved."""
    SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCORES_FILE.write_text(csv_text.strip(), encoding="utf-8")
    return sum(1 for _ in csv.DictReader(io.StringIO(csv_text.strip())))

# ── Playlist I/O ─────────────────────────────────────────────────────────────────

def load_playlist() -> list:
    """Load playlist entries from JSON. Returns empty list if no file exists."""
    if not PLAYLIST_FILE.exists():
        return []
    entries = json.loads(PLAYLIST_FILE.read_text(encoding="utf-8"))
    for e in entries:
        e.setdefault("tags", [])
    return entries


def save_playlist(entries: list) -> None:
    PLAYLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    PLAYLIST_FILE.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")


def scrape_song_page(url: str) -> dict:
    """
    Fetch a 3icecream.com song details page and extract chart info.

    Returns:
        {song_id, song_name, charts: [{difficulty, rating, youtube_url}]}
        Only charts with rating >= 10 are included.
    """
    m = re.search(r'/song_details/([A-Za-z0-9]+)', url)
    if not m:
        raise ValueError(f"Could not find a song ID in URL: {url}")
    song_id = m.group(1)

    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        html = resp.read().decode("utf-8")

    # Song title
    mt = re.search(r'<span class="sp-title outlined color-vibrant-main">([^<]+)</span>', html)
    song_name = mt.group(1).strip() if mt else "Unknown"

    # Difficulty names indexed by color number (0=BEG … 4=CSP)
    diff_names = {m.group(1): m.group(2)
                  for m in re.finditer(r'sp-difficulty-name diff-color-(\d)">([A-Z]+)<', html)}

    # Ratings indexed by color number
    ratings = {m.group(1): int(m.group(2))
               for m in re.finditer(r'sp-difficulty diff-color-(\d)">(\d+)<', html)}

    # YouTube URLs indexed by div-share id ("0-N" → index N)
    youtube_urls = {}
    for block_m in re.finditer(
        r'<div class="div-share" id="0-(\d)">(.*?)</div>', html, re.DOTALL
    ):
        idx   = block_m.group(1)
        block = block_m.group(2)
        yt    = re.search(r'href="(https://www\.youtube\.com/watch\?v=[^"]+)"', block)
        if yt:
            youtube_urls[idx] = yt.group(1)

    charts = []
    for idx in sorted(diff_names):
        rating = ratings.get(idx)
        if rating is None or rating < 10:
            continue
        charts.append({
            "difficulty":  DIFF_ABBREV.get(diff_names[idx], diff_names[idx]),
            "rating":      rating,
            "youtube_url": youtube_urls.get(idx),
        })

    return {"song_id": song_id, "song_name": song_name, "charts": charts}


# ── Display helpers ───────────────────────────────────────────────────────────────

def format_level(level: int, songs: list) -> str:
    reqs    = PLATINUM[level]["main"]
    subs    = PLATINUM[level]["subs"]
    results = [evaluate(r, songs) for r in reqs]
    met     = sum(1 for m, _, _ in results if m is True)
    total   = sum(1 for m, _, _ in results if m is not None)

    lines = [f"PLATINUM {ROMAN[level]}  ({met}/{total} assessable requirements met)", ""]
    lines.append("Main requirements:")
    for req, (m, progress, detail) in zip(reqs, results):
        line = f"  {ICON[m]} {req['label']:<42} {progress}"
        if detail:
            line += f"  · {detail}"
        lines.append(line)
    lines += ["", "Substitutions:"]
    for sub in subs:
        m, progress, detail = evaluate(sub, songs)
        line = f"  {ICON[m]} {sub['label']:<42} {progress}"
        if detail and not m:
            line += f"  · {detail}"
        lines.append(line)
    return "\n".join(lines)


def parse_volume_progress(progress: str) -> tuple[int, int]:
    current, total = progress.split("/")
    return int(current.strip()), int(total.strip())


def parse_score_gap(progress: str):
    """Extract numeric gap from '935,400  (need +24,600)'. Returns int or None."""
    if "need +" not in progress:
        return None
    try:
        raw = progress.split("need +")[1].replace(",", "").replace(")", "").strip()
        return int(raw)
    except (ValueError, IndexError):
        return None

# ── Tools ─────────────────────────────────────────────────────────────────────────

@mcp.tool()
def check_progress(level: int = 0) -> str:
    """
    Check your Life4 Platinum rank progress.

    Args:
        level: Platinum level to check (1–5). Pass 0 or omit for an overview of all levels.
    """
    songs = load_scores()
    if songs is None:
        return "No score data on file. Use upload_scores to submit your CSV export."

    if 1 <= level <= 5:
        return format_level(level, songs)

    lines = [f"Loaded {len(songs)} score entries.\n", "OVERVIEW"]
    for lvl in range(1, 6):
        reqs    = PLATINUM[lvl]["main"]
        results = [evaluate(r, songs) for r in reqs]
        met     = sum(1 for m, _, _ in results if m is True)
        total   = sum(1 for m, _, _ in results if m is not None)
        icon    = "✅" if met == total else ("🔶" if met > 0 else "❌")
        lines.append(f"  {icon}  Platinum {ROMAN[lvl]:<5}  {met}/{total} met  (Trials excluded)")
    return "\n".join(lines)


@mcp.tool()
def get_focus() -> str:
    """
    Get a prioritized list of what to focus on during your next DDR play session,
    based on your current scores and Platinum progress.
    """
    songs = load_scores()
    if songs is None:
        return "No score data on file. Use upload_scores to submit your CSV export."

    # Find the first unfinished platinum level
    target = None
    for lvl in range(1, 6):
        reqs    = PLATINUM[lvl]["main"]
        results = [evaluate(r, songs) for r in reqs]
        if any(m is False for m, _, _ in results):
            target = lvl
            break

    if target is None:
        return "All assessable requirements for Platinum V are met! Check Trials manually."

    reqs    = PLATINUM[target]["main"]
    results = [evaluate(r, songs) for r in reqs]
    unmet   = [(r, p, d) for r, (m, p, d) in zip(reqs, results) if m is False]

    immediate, session, grind = [], [], []

    for req, progress, detail in unmet:
        label = req["label"]
        t     = req["type"]

        if t == "volume":
            current, total = parse_volume_progress(progress)
            remaining = total - current
            entry = (label, progress, detail)
            if remaining <= 2:
                immediate.append((*entry, f"Only {remaining} more needed!"))
            elif current / total >= 0.5:
                session.append((*entry, f"{remaining} more — solid session goal"))
            else:
                grind.append((*entry, f"{remaining} more — longer-term grind"))

        elif t == "peak":
            gap   = parse_score_gap(progress)
            entry = (label, progress, detail)
            if gap is not None and gap <= 20_000:
                immediate.append((*entry, "Gap under 20k — very reachable!"))
            elif gap is not None and gap <= 50_000:
                session.append((*entry, "Gap under 50k — solid session goal"))
            else:
                grind.append((*entry, "Large score gap — longer term"))

        elif t in ("aaa", "pfc"):
            current, total = parse_volume_progress(progress)
            grind.append((label, progress, detail, f"Need {total - current} more"))

    lines = [f"🎮 Target: Platinum {ROMAN[target]}", ""]

    if immediate:
        lines.append("🎯 FINISH THESE FIRST:")
        for label, progress, detail, note in immediate:
            lines.append(f"  • {label}  [{progress}]")
            lines.append(f"    → {note}")
            if detail:
                lines.append(f"    ↳ {detail}")
        lines.append("")

    if session:
        lines.append("📈 GOOD SESSION GOALS:")
        for label, progress, detail, note in session:
            lines.append(f"  • {label}  [{progress}]")
            lines.append(f"    → {note}")
            if detail:
                lines.append(f"    ↳ {detail}")
        lines.append("")

    if grind:
        lines.append("🔁 KEEP CHIPPING AWAY:")
        for label, progress, detail, note in grind:
            lines.append(f"  • {label}  [{progress}]")
            lines.append(f"    → {note}")
        lines.append("")

    lines.append("Tip: ask check_progress to see substitution options.")
    return "\n".join(lines)


@mcp.tool()
def upload_scores(csv_text: str) -> str:
    """
    Upload your DDR score data. Paste the full text of your CSV export from 3icecream.com.

    Args:
        csv_text: Full text content of your scores CSV export.
    """
    try:
        reader   = csv.DictReader(io.StringIO(csv_text.strip()))
        required = {"Song ID", "Song Name", "Difficulty", "Rating", "Score", "Grade", "Lamp"}
        missing  = required - set(reader.fieldnames or [])
        if missing:
            return f"Error: CSV is missing required columns: {', '.join(sorted(missing))}"
        rows = list(reader)
        if not rows:
            return "Error: CSV has no data rows."
        int(rows[0]["Rating"])
        int(rows[0]["Score"])
    except Exception as e:
        return f"Error parsing CSV: {e}"

    n = save_scores(csv_text)
    return f"✅ Saved {n} score entries. Run check_progress to see your updated stats."


# ── Playlist tools ───────────────────────────────────────────────────────────────

@mcp.tool()
def add_to_playlist(url: str, difficulty: str) -> str:
    """
    Add a specific chart from a 3icecream.com song page to your practice playlist.

    Args:
        url:        A 3icecream.com song details URL, e.g.
                    https://3icecream.com/ddr/song_details/SONG_ID
        difficulty: The chart to add: DSP, ESP, or CSP.
    """
    try:
        song = scrape_song_page(url)
    except Exception as e:
        return f"Error fetching song page: {e}"

    diff_upper = difficulty.upper().strip()
    chart = next((c for c in song["charts"] if c["difficulty"] == diff_upper), None)

    if chart is None:
        available = ", ".join(f"{c['difficulty']} (lv{c['rating']})" for c in song["charts"])
        if available:
            return f"No {diff_upper} chart found for {song['song_name']}. Available: {available}"
        return f"No charts rated 10+ found for {song['song_name']}."

    playlist = load_playlist()
    exists = any(
        e["song_id"] == song["song_id"] and e["difficulty"] == diff_upper
        for e in playlist
    )
    if exists:
        return f"⏭  {song['song_name']} [{diff_upper}] is already on your playlist."

    playlist.append({
        "song_id":     song["song_id"],
        "song_name":   song["song_name"],
        "difficulty":  chart["difficulty"],
        "rating":      chart["rating"],
        "youtube_url": chart["youtube_url"],
    })
    save_playlist(playlist)
    return f"✅ Added {song['song_name']} [{diff_upper} lv{chart['rating']}] to your playlist."


@mcp.tool()
def get_playlist(level: int = 0, tag: str = "") -> str:
    """
    Show your practice playlist.

    Args:
        level: Filter by rating (e.g. 14 shows only lv14 charts). Pass 0 or omit for all.
        tag:   Filter by tag (e.g. "crossover"). Leave blank for all tags.
    """
    playlist = load_playlist()
    if not playlist:
        return "Your playlist is empty. Use add_to_playlist with a 3icecream.com URL to add songs."

    tag_lower = tag.lower().strip()
    entries = [
        e for e in playlist
        if (level == 0 or e["rating"] == level)
        and (not tag_lower or tag_lower in e["tags"])
    ]

    if not entries:
        desc = " and ".join(filter(None, [f"lv{level}" if level else "", f'tag "{tag}"' if tag else ""]))
        return f"No charts matching {desc} on your playlist."

    header_parts = filter(None, [f"lv{level}" if level else "", f'#{tag}' if tag else ""])
    header = f"Practice playlist{' — ' + ', '.join(header_parts) if any(header_parts) else ''} ({len(entries)} charts)"
    lines  = [header, ""]

    by_rating: dict[int, list] = {}
    for e in entries:
        by_rating.setdefault(e["rating"], []).append(e)

    for rating in sorted(by_rating):
        if level == 0:
            lines.append(f"── Level {rating} ──")
        for e in by_rating[rating]:
            yt      = f"  🎬 {e['youtube_url']}" if e["youtube_url"] else ""
            tags    = f"  [{', '.join(e['tags'])}]" if e["tags"] else ""
            lines.append(f"  {e['song_name']}  [{e['difficulty']}]{tags}{yt}")
        if level == 0:
            lines.append("")

    return "\n".join(lines)


@mcp.tool()
def remove_from_playlist(song_name: str, difficulty: str = "") -> str:
    """
    Remove a song from your practice playlist.

    Args:
        song_name: Song name (case-insensitive, partial match is fine).
        difficulty: Specific difficulty to remove (e.g. ESP). Leave blank to remove all
                    difficulties for the matched song.
    """
    playlist = load_playlist()
    if not playlist:
        return "Your playlist is empty."

    name_lower = song_name.lower()
    diff_upper = difficulty.upper().strip()

    matches   = [e for e in playlist if name_lower in e["song_name"].lower()]
    if not matches:
        return f"No songs matching '{song_name}' found on your playlist."

    if diff_upper:
        to_remove = [e for e in matches if e["difficulty"] == diff_upper]
        if not to_remove:
            found_diffs = ", ".join(sorted({e["difficulty"] for e in matches}))
            return (f"No {diff_upper} chart found for '{matches[0]['song_name']}'. "
                    f"Available: {found_diffs}")
    else:
        to_remove = matches

    new_playlist = [e for e in playlist if e not in to_remove]
    save_playlist(new_playlist)

    removed_desc = ", ".join(
        f"{e['difficulty']} (lv{e['rating']})" for e in to_remove
    )
    return f"✅ Removed from playlist: {to_remove[0]['song_name']} — {removed_desc}"


# ── Tagging tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def tag_song(song_name: str, tags: str, difficulty: str = "") -> str:
    """
    Add tags to a song on your practice playlist.

    Args:
        song_name:  Song name (case-insensitive, partial match is fine).
        tags:       Comma-separated tags to add, e.g. "crossover, favorite".
        difficulty: Scope to a specific difficulty (e.g. ESP). Leave blank to tag all
                    matching difficulties for the song.
    """
    playlist = load_playlist()
    new_tags  = [t.strip().lower() for t in tags.split(",") if t.strip()]
    if not new_tags:
        return "No valid tags provided."

    name_lower = song_name.lower()
    diff_upper = difficulty.upper().strip()
    matches    = [e for e in playlist if name_lower in e["song_name"].lower()]
    if not matches:
        return f"No songs matching '{song_name}' found on your playlist."

    if diff_upper:
        targets = [e for e in matches if e["difficulty"] == diff_upper]
        if not targets:
            found = ", ".join(sorted({e["difficulty"] for e in matches}))
            return f"No {diff_upper} chart for '{matches[0]['song_name']}'. Available: {found}"
    else:
        targets = matches

    for e in targets:
        e["tags"] = sorted(set(e["tags"]) | set(new_tags))

    save_playlist(playlist)
    desc = ", ".join(f"{e['difficulty']} (lv{e['rating']})" for e in targets)
    return f"✅ Tagged {targets[0]['song_name']} [{desc}] with: {', '.join(new_tags)}"


@mcp.tool()
def untag_song(song_name: str, tags: str, difficulty: str = "") -> str:
    """
    Remove tags from a song on your practice playlist.

    Args:
        song_name:  Song name (case-insensitive, partial match is fine).
        tags:       Comma-separated tags to remove, e.g. "crossover".
        difficulty: Scope to a specific difficulty (e.g. ESP). Leave blank to untag all
                    matching difficulties for the song.
    """
    playlist   = load_playlist()
    remove_tags = [t.strip().lower() for t in tags.split(",") if t.strip()]
    if not remove_tags:
        return "No valid tags provided."

    name_lower = song_name.lower()
    diff_upper = difficulty.upper().strip()
    matches    = [e for e in playlist if name_lower in e["song_name"].lower()]
    if not matches:
        return f"No songs matching '{song_name}' found on your playlist."

    if diff_upper:
        targets = [e for e in matches if e["difficulty"] == diff_upper]
        if not targets:
            found = ", ".join(sorted({e["difficulty"] for e in matches}))
            return f"No {diff_upper} chart for '{matches[0]['song_name']}'. Available: {found}"
    else:
        targets = matches

    for e in targets:
        e["tags"] = [t for t in e["tags"] if t not in remove_tags]

    save_playlist(playlist)
    desc = ", ".join(f"{e['difficulty']} (lv{e['rating']})" for e in targets)
    return f"✅ Removed tags [{', '.join(remove_tags)}] from {targets[0]['song_name']} [{desc}]"


# ── Auth middleware ───────────────────────────────────────────────────────────────

class AuthMiddleware:
    """
    Pure ASGI middleware — accepts requests authenticated by either:
      - Authorization: Bearer <API_KEY> header  (Claude Code, curl)
      - URL path prefix /<API_KEY>/...          (Claude.ai connectors)

    When the URL prefix form is used, the prefix is stripped before the
    request is forwarded so the MCP app always sees paths starting with /mcp.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket") or not API_KEY:
            await self.app(scope, receive, send)
            return

        path    = scope.get("path", "")
        prefix  = f"/{API_KEY}"
        headers = dict(scope.get("headers", []))
        auth    = headers.get(b"authorization", b"").decode()

        if path.startswith(prefix):
            # Strip the secret prefix so MCP app sees /mcp/...
            new_path = path[len(prefix):] or "/"
            scope = {**scope, "path": new_path,
                     "raw_path": new_path.encode()}
        elif auth.startswith("Bearer ") and auth[7:] == API_KEY:
            pass  # bearer token is valid — forward as-is
        else:
            await PlainTextResponse("Unauthorized", status_code=401)(scope, receive, send)
            return

        await self.app(scope, receive, send)


# ── App assembly ──────────────────────────────────────────────────────────────────

def build_app():
    # Build the MCP app without Starlette routing to avoid trailing-slash redirects
    # and path-stripping that break the session manager.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    session_manager = StreamableHTTPSessionManager(
        app=mcp._mcp_server,
        security_settings=security,
    )

    class MCPApp:
        """Bare ASGI app: handles lifespan to init the session manager task group,
        and delegates all HTTP/WS requests directly to the session manager."""
        async def __call__(self, scope, receive, send):
            if scope["type"] == "lifespan":
                await receive()  # lifespan.startup
                async with session_manager.run():
                    await send({"type": "lifespan.startup.complete"})
                    await receive()  # lifespan.shutdown
                await send({"type": "lifespan.shutdown.complete"})
            else:
                await session_manager.handle_request(scope, receive, send)

    return AuthMiddleware(MCPApp())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(build_app(), host="0.0.0.0", port=port)
