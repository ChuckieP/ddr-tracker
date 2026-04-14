# DDR Life4 Platinum Tracker

Track your DDR progress toward Life4 Platinum ranks (I–V). Runs as a local CLI tool or as a remote MCP server accessible from any Claude chat — including on your phone.

---

## Local CLI

### Setup

Requires Python 3. No dependencies beyond the standard library.

## Usage

```bash
# Full report — all Platinum levels
python3 tracker.py

# Detailed report for a specific level
python3 tracker.py 1

# Specify a CSV file explicitly
python3 tracker.py my_export.csv

# Combine both
python3 tracker.py my_export.csv 1
```

## Updating Your Scores

1. Export your scores from [3icecream.com](https://3icecream.com) after each play session
2. Save the CSV to this folder with a filename starting with `scores` (e.g. `scores_csv.csv`)
3. Re-run the tracker — it automatically picks up the most recently modified `scores*.csv`

## Score Export Format

The tracker expects a CSV with the following columns:

| Column | Description |
|---|---|
| Song ID | Unique song identifier |
| Song Name | Song title |
| Difficulty | Chart type (ESP, DSP, CSP, etc.) |
| Rating | Song level (e.g. 14, 15, 16) |
| Score | Numeric score (0–1,000,000) |
| Grade | Letter grade (B+, A, AA, etc.) |
| Lamp | Clear type: `Fail`, `Clear`, `FC`, `GFC`, `PFC` |

## Requirement Types

| Type | Description |
|---|---|
| Volume clear | Clear N songs at a given level with a minimum score. Some slots allow **exceptions** — songs that only need a lower score (or a basic clear) to count. |
| Peak score | Achieve a minimum score on any single song at a given level. |
| AAA | Score 990,000+ on N songs at a given level. |
| PFC | Achieve a Perfect Full Combo lamp on N songs at a given level or above. |
| Trial | Earn a tier on a Life4 Trial. **Not tracked from the CSV** — shown as `?`. |

## Substitutions

Each Platinum level has a substitution pool. Any number of main requirements can be swapped 1-for-1 with substitutions from the pool. The tracker reports substitution progress separately so you can plan which combination to target.

## Output Guide

```
✅  Requirement met
❌  Requirement not yet met
🔶  Some progress made (overview only)
❓  Cannot be assessed from export (Trials)
```

For volume clears, the detail column shows how many songs qualify at the main threshold vs. exception threshold, e.g.:

```
❌  Clear 60 lv14s @ 810k+    11/60  · 10 main + 1 exc
```

---

## Remote MCP Server (Claude Tools — any device)

`server.py` runs as a remote MCP server so you can use your tracker from any Claude chat, including Claude.ai on your phone.

### Tools available

| Tool | What it does |
|---|---|
| `check_progress` | Reports your Platinum progress (all levels, or a specific level 1–5) |
| `get_focus` | Recommends what to focus on in your next play session |
| `upload_scores` | Accepts pasted CSV text and stores it server-side |

### Deploying to Railway

**1. Install the Railway CLI and log in**
```bash
brew install railway
railway login
```

**2. Initialize and deploy from this folder**
```bash
cd /path/to/ddr-tracker
railway init       # creates a new Railway project
railway up         # deploys the server
```

**3. Generate a secret API key**
```bash
openssl rand -hex 32
```

**4. Set environment variables in Railway**
```bash
railway variables set DDR_API_KEY=<your-generated-key>
```

**5. Get your deployment URL**
```bash
railway domain
# e.g. https://ddr-tracker-production-abc1.up.railway.app
```

**6. (Recommended) Add a persistent volume for score storage**

By default, uploaded scores are stored in `/data/scores.csv`. On Railway's free tier, this resets on each redeploy — you'd need to re-upload your scores after deploying a new version. To make storage persistent:
- Go to your project in the [Railway dashboard](https://railway.app)
- Add a Volume and mount it at `/data`
- That's it — scores will survive redeploys

### Connecting to Claude.ai

1. Go to **Claude.ai → Settings → Integrations**
2. Click **Add MCP Server**
3. Enter your Railway URL: `https://your-app.up.railway.app/mcp`
4. Add a custom header:
   - Name: `Authorization`
   - Value: `Bearer <your-api-key>`
5. Save — the tools will now be available in any Claude.ai conversation

### Using from your phone at the arcade

**After a play session — upload new scores:**
1. Visit [3icecream.com](https://3icecream.com) on your phone and export your scores as CSV
2. Open Claude.ai and say: *"Upload my scores"* then paste the CSV text
3. Claude will call `upload_scores` and confirm the save

**Before a session — get focus recommendations:**
> *"What should I focus on today?"*

**Check your progress anytime:**
> *"Check my Platinum progress"*
> *"How am I doing on Platinum I?"*
