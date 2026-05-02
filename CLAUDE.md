# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DDR Life4 Platinum Tracker — a tool for tracking progress toward Dance Dance Revolution Life4 Platinum rank (levels I–V). Runs as both a local CLI and a Railway-deployed MCP server accessible from Claude.ai.

## Common Commands

```bash
# Run the local CLI tracker
python3 tracker.py                        # Auto-find latest scores*.csv, full report
python3 tracker.py 3                      # Detailed report for Platinum level 3
python3 tracker.py scores_csv.csv 2       # Explicit file + level

# Run the MCP server locally (requires pip install -r requirements.txt)
python3 server.py

# Deploy to Railway
railway up

# Set environment variable in Railway
railway variables set DDR_API_KEY=<key>
```

No test suite or linter is configured.

## Architecture

Two entry points sharing a common scoring engine:

**`tracker.py`** — Standalone CLI. Contains all shared logic:
- `PLATINUM` dict: hardcoded requirements for all 5 Platinum levels
- `load_scores(csv_path)` — parses 3icecream.com CSV exports
- `evaluate(req, songs)` — core evaluation returning `(met, progress, detail)` for requirement types: `volume`, `peak`, `aaa`, `pfc`, `trial`

**`server.py`** — Railway-deployed MCP server. Imports `PLATINUM`, `ROMAN`, `ICON`, `AAA_SCORE`, `evaluate` from `tracker.py`. Adds 6 MCP tools via `@mcp.tool()` decorators, a REST layer (Starlette + Uvicorn), `AuthMiddleware`, and playlist management.

### MCP Tools
| Tool | Purpose |
|------|---------|
| `check_progress(level=0)` | Overview of all levels or detailed report |
| `get_focus()` | Session recommendations with ceiling/floor framing based on current progress |
| `upload_scores(csv_text)` | Accept pasted CSV, validate & store |
| `add_to_playlist(url, difficulty)` | Scrape 3icecream.com song page, store the specified chart (DSP/ESP/CSP) |
| `get_playlist(level=0)` | Display playlist, optionally filtered by level |
| `remove_from_playlist(song_name, difficulty="")` | Remove by partial name match |

### Storage
- Local: reads/writes from current directory (`scores*.csv`, `playlist.json`)
- Server: `/data/scores.csv` and `/data/playlist.json` (Railway persistent volume)
- **A Railway volume must be mounted at `/data`** — without it, data resets on every deploy. Create with: `railway volume add --mount-path /data`

### Authentication
`AuthMiddleware` in `server.py` supports two modes simultaneously:
- Bearer token: `Authorization: Bearer <DDR_API_KEY>`
- URL prefix: `/<DDR_API_KEY>/mcp/...` (used by Claude.ai connectors, prefix stripped before MCP sees the request)

### Requirement Types (in `evaluate()`)
- **`volume`**: count songs at level with score ≥ threshold; supports `exc` exception slots at a lower `exc_score`
- **`peak`**: highest score at a level must reach threshold
- **`aaa`**: count songs at level with score ≥ 990,000
- **`pfc`**: count songs at level_min+ with lamp == "PFC"
- **`trial`**: untrackable from CSV; always returns `None`

`peak` maps to **ceiling work** (pushing your best score on a specific chart); `volume`, `aaa`, and `pfc` map to **floor work** (consistency across many songs). `get_focus` uses this distinction to recommend a session type. See https://iidx.org/theory/skill_ceiling_floor for the source theory.

Each Platinum level has 9 main requirements (1 untrackable trial) and ~5 substitution options (1-for-1 swaps allowed).

## Claude.ai MCP Connection

```
Settings → Integrations → Add MCP Server
URL: https://<railway-app>.up.railway.app/mcp
Custom Header:
  Name: Authorization
  Value: Bearer <DDR_API_KEY>
```

## Data Source

Scores are exported from [3icecream.com](https://3icecream.com) as CSV. The playlist scraper also fetches HTML from 3icecream.com song pages using stdlib `re` + `urllib.request` (no BeautifulSoup).
