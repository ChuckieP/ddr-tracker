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
import os
import uvicorn
from pathlib import Path
from starlette.responses import PlainTextResponse
from mcp.server.fastmcp import FastMCP
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

# Shared evaluation logic lives in tracker.py
from tracker import PLATINUM, ROMAN, ICON, AAA_SCORE, evaluate

# ── Config ───────────────────────────────────────────────────────────────────────

SCORES_FILE = Path(os.environ.get("SCORES_PATH", "/data/scores.csv"))
API_KEY     = os.environ.get("DDR_API_KEY", "")

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
