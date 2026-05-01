#!/usr/bin/env python3
"""
DDR Life4 Rank Progress Tracker
Usage: python tracker.py [csv_file] [rank]
  csv_file — path to scores CSV export (default: latest scores*.csv in current dir)
  rank     — rank to report on, e.g. platinum1, gold3, "Platinum III"
             (default: show overview + detail for all Platinum levels)
"""

import csv
import json
import sys
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────────

AAA_SCORE = 990_000
ROMAN     = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}
ICON      = {True: "✅", False: "❌", None: "❓"}

_INT_TO_ROMAN = {v: k for k, v in ROMAN.items()}

RANK_TIERS = [
    "copper", "bronze", "silver", "gold", "platinum",
    "diamond", "cobalt", "pearl", "topaz", "amethyst",
    "emerald", "onyx", "ruby",
]

# ── Rank name handling ────────────────────────────────────────────────────────────

def normalize_rank_name(s: str) -> str | None:
    """
    Accept flexible rank names and return the canonical 'tier#' key.
    Examples: "platinum1", "Platinum I", "platinum 1", "gold_3" → "platinum1", "gold3"
    Returns None if unrecognized.
    """
    s = s.strip().lower().replace("_", " ").replace("-", " ")
    tier = None
    for t in RANK_TIERS:
        if t in s:
            tier = t
            s = s.replace(t, "").strip()
            break
    if tier is None:
        return None
    if s.isdigit() and 1 <= int(s) <= 5:
        return f"{tier}{s}"
    upper = s.upper()
    if upper in _INT_TO_ROMAN:
        return f"{tier}{_INT_TO_ROMAN[upper]}"
    return None


def rank_display_name(rank_key: str) -> str:
    """'platinum1' → 'PLATINUM I'"""
    for tier in RANK_TIERS:
        if rank_key.startswith(tier):
            num = int(rank_key[len(tier):])
            return f"{tier.upper()} {ROMAN[num]}"
    return rank_key.upper()

# ── Rank data loading ─────────────────────────────────────────────────────────────

_RANK_DATA: dict | None = None


def _goal_to_req(goal: dict) -> dict:
    """Convert a pprx goal object to a tracker requirement dict."""
    if goal["t"] == "trial":
        tier  = goal["rank"].title()
        count = goal["count"]
        s     = "s" if count > 1 else ""
        return {"type": "trial", "label": f"{tier}+ on {count} Trial{s}"}

    if goal["t"] in ("calories", "ma_points", "set"):
        return {"type": "untrackable", "label": f"{goal['t'].replace('_', ' ').title()} requirement"}

    d      = goal["d"]
    ct     = goal.get("clear_type")
    count  = goal.get("song_count")
    score  = goal.get("score")
    exc    = goal.get("exceptions", 0)
    exc_sc = goal.get("exception_score")
    higher = goal.get("higher_diff", False)
    lvl_s  = f"{d}+" if higher else f"{d}s"

    # PFC requirement
    if ct == "perfect":
        n = count or 1
        plural = f" {n}" if n > 1 else ""
        return {"type": "pfc", "level_min": d, "count": n,
                "label": f"PFC{plural} lv{lvl_s}"}

    # GFC (count-based, with or without higher_diff) — trackable
    if ct == "good" and count is not None:
        n = count
        plural = f" {n}" if n > 1 else ""
        return {"type": "gfc", "level": d, "count": n, "higher_diff": higher,
                "label": f"GFC{plural} lv{lvl_s}"}

    # GFC all-songs variant (no song_count), life4, sdp, great — not in CSV export
    if ct in ("good", "life4", "sdp", "great"):
        return {"type": "untrackable", "label": f"{ct.upper()} requirement lv{d}"}

    # "All songs at level" (no song_count, has score) — total unknown from CSV
    if count is None:
        return {"type": "untrackable", "label": f"Score {score // 1000}k+ on all lv{d}s"}

    # Clear (no score threshold)
    if score is None:
        label = f"Clear a lv{d}" if count == 1 else f"Clear {count} lv{d}s"
        return {"type": "volume", "level": d, "count": count, "score": None,
                "exc": exc, "exc_score": exc_sc, "label": label}

    # Single-song score requirement (peak)
    if count == 1:
        label = "AAA" if score == AAA_SCORE else f"{score // 1000}k+"
        return {"type": "peak", "level": d, "score": score,
                "label": f"{label} on a lv{d}"}

    # Multi-song AAA
    if score >= AAA_SCORE:
        return {"type": "aaa", "level": d, "count": count,
                "label": f"AAA {count} lv{d}s"}

    # Volume with score threshold
    return {"type": "volume", "level": d, "count": count, "score": score,
            "exc": exc, "exc_score": exc_sc,
            "label": f"Clear {count} lv{d}s @ {score // 1000}k+"}


def _load_rank_data() -> dict:
    global _RANK_DATA
    if _RANK_DATA is not None:
        return _RANK_DATA
    path = Path(__file__).parent / "ranks.json"
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    goals   = {g["id"]: g for g in raw["goals"]}
    out     = {}
    for rr in raw["rank_requirements"]:
        name = rr["rank"]
        out[name] = {
            "main": [_goal_to_req(goals[gid]) for gid in rr["mandatory_goal_ids"]],
            "subs": [_goal_to_req(goals[gid]) for gid in rr.get("substitutions", [])],
        }
    _RANK_DATA = out
    return _RANK_DATA


def get_rank_reqs(rank_name: str) -> dict | None:
    """Return {'main': [...], 'subs': [...]} for the given rank, or None if unrecognized."""
    key = normalize_rank_name(rank_name) if rank_name not in _load_rank_data() else rank_name
    if key is None:
        return None
    return _load_rank_data().get(key)

# ── Score loading ─────────────────────────────────────────────────────────────────

def load_scores(csv_path):
    songs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
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

# ── Evaluation ───────────────────────────────────────────────────────────────────

def evaluate(req, songs):
    """
    Returns (met, progress, detail)
      met      — True/False/None (None = untrackable)
      progress — short progress string
      detail   — optional extra context
    """
    t = req["type"]

    if t == "volume":
        level        = req["level"]
        count        = req["count"]
        score_thresh = req.get("score")
        exc          = req.get("exc", 0)
        exc_score    = req.get("exc_score")

        cleared = [s for s in songs if s["level"] == level and s["lamp"] != "Fail"]

        if score_thresh is None:
            n = len(cleared)
            return n >= count, f"{n}/{count}", ""

        main = [s for s in cleared if s["score"] >= score_thresh]

        if exc > 0:
            if exc_score is not None:
                exc_pool = [s for s in cleared if exc_score <= s["score"] < score_thresh]
            else:
                exc_pool = [s for s in cleared if s["score"] < score_thresh]
            used_exc = min(len(exc_pool), exc)
        else:
            exc_pool = []
            used_exc = 0

        effective = len(main) + used_exc
        detail    = f"{len(main)} main + {used_exc} exc" if used_exc > 0 else ""
        return effective >= count, f"{effective}/{count}", detail

    elif t == "peak":
        level        = req["level"]
        score_thresh = req["score"]
        lvl_songs    = [s for s in songs if s["level"] == level]
        if not lvl_songs:
            return False, "–", f"no lv{level} scores"
        best = max(lvl_songs, key=lambda s: s["score"])
        met  = best["score"] >= score_thresh
        gap  = f"  (need +{score_thresh - best['score']:,})" if not met else " ✓"
        return met, f"{best['score']:,}{gap}", best["name"] if not met else ""

    elif t == "aaa":
        level     = req["level"]
        count     = req["count"]
        aaa_list  = [s for s in songs if s["level"] == level and s["score"] >= AAA_SCORE]
        n         = len(aaa_list)
        lvl_songs = [s for s in songs if s["level"] == level]
        if lvl_songs and n < count:
            best   = max(lvl_songs, key=lambda s: s["score"])
            detail = f"best: {best['score']:,}  (need +{AAA_SCORE - best['score']:,})"
        else:
            detail = ""
        return n >= count, f"{n}/{count}", detail

    elif t == "pfc":
        level_min = req["level_min"]
        count     = req["count"]
        pfcs      = [s for s in songs if s["level"] >= level_min and s["lamp"] == "PFC"]
        n         = len(pfcs)
        if n < count:
            near   = [s for s in songs if s["level"] >= level_min and s["lamp"] in ("MFC", "GFC", "FC")]
            detail = (f"best lamp: {max(near, key=lambda s: s['score'])['lamp']} on "
                      f"{max(near, key=lambda s: s['score'])['name']} lv{max(near, key=lambda s: s['score'])['level']}"
                      if near else "no FC lamps yet at this level")
        else:
            detail = ""
        return n >= count, f"{n}/{count}", detail

    elif t == "gfc":
        level  = req["level"]
        count  = req["count"]
        higher = req.get("higher_diff", False)
        gfc_lamps = ("GFC", "PFC", "MFC")
        if higher:
            gfcs = [s for s in songs if s["level"] >= level and s["lamp"] in gfc_lamps]
        else:
            gfcs = [s for s in songs if s["level"] == level and s["lamp"] in gfc_lamps]
        n = len(gfcs)
        return n >= count, f"{n}/{count}", ""

    elif t in ("trial", "untrackable"):
        return None, "?", "not in export"

    return False, "?", ""

# ── Display ──────────────────────────────────────────────────────────────────────

def print_rank_report(rank_key: str, songs: list):
    reqs_data = get_rank_reqs(rank_key)
    if reqs_data is None:
        print(f"Unknown rank: '{rank_key}'")
        return

    display = rank_display_name(rank_key)
    reqs    = reqs_data["main"]
    subs    = reqs_data["subs"]

    results    = [evaluate(r, songs) for r in reqs]
    met_count  = sum(1 for met, _, _ in results if met is True)
    assessable = sum(1 for met, _, _ in results if met is not None)

    print(f"\n{'─' * 62}")
    print(f"  {display}   ({met_count}/{assessable} assessable requirements met)")
    print(f"{'─' * 62}")

    print("  Main requirements:")
    for req, (met, progress, detail) in zip(reqs, results):
        line = f"    {ICON[met]}  {req['label']:<42} {progress}"
        if detail:
            line += f"  · {detail}"
        print(line)

    print("\n  Substitutions:")
    for sub in subs:
        met, progress, detail = evaluate(sub, songs)
        line = f"    {ICON[met]}  {sub['label']:<42} {progress}"
        if detail and not met:
            line += f"  · {detail}"
        print(line)


def print_summary(songs: list):
    print("\n" + "═" * 62)
    print("  DDR Life4 Platinum — Overview")
    print("═" * 62)
    for n in range(1, 6):
        rank_key  = f"platinum{n}"
        reqs      = get_rank_reqs(rank_key)["main"]
        results   = [evaluate(r, songs) for r in reqs]
        met       = sum(1 for m, _, _ in results if m is True)
        total     = sum(1 for m, _, _ in results if m is not None)
        icon      = "✅" if met == total else ("🔶" if met > 0 else "❌")
        print(f"  {icon}  Platinum {ROMAN[n]:<5}  {met}/{total} met  (Trials excluded)")

# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    csv_path  = None
    rank_args = []

    for arg in sys.argv[1:]:
        if Path(arg).exists():
            csv_path = arg
        else:
            rank_args.append(arg)

    rank_key = None
    if rank_args:
        candidate = " ".join(rank_args)
        rank_key  = normalize_rank_name(candidate)
        if rank_key is None:
            print(f"Warning: '{candidate}' is not a recognized rank name. "
                  f"Examples: platinum1, gold3, 'Platinum III'")

    if csv_path is None:
        candidates = sorted(Path(".").glob("scores*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("Error: no scores CSV found. Pass the file path as an argument.")
            sys.exit(1)
        csv_path = candidates[0]
        print(f"Using: {csv_path}")

    songs = load_scores(csv_path)
    print(f"Loaded {len(songs)} score entries.\n")

    if rank_key:
        print_rank_report(rank_key, songs)
    else:
        print_summary(songs)
        for n in range(1, 6):
            print_rank_report(f"platinum{n}", songs)

    print()


if __name__ == "__main__":
    main()
