#!/usr/bin/env python3
"""
DDR Life4 Platinum Progress Tracker
Usage: python tracker.py [csv_file] [1-5]
  csv_file  — path to scores CSV export (default: latest scores*.csv in current dir)
  1-5       — show detailed report for a specific Platinum level only
"""

import csv
import sys
from pathlib import Path

# ── Constants ────────────────────────────────────────────────────────────────────

AAA_SCORE = 990_000
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V"}

# ── Requirements ─────────────────────────────────────────────────────────────────
#
# Requirement types:
#   volume — clear N songs at given level; score = min score (None = any clear)
#            exc = # exception slots, exc_score = min score for exceptions (None = basic clear)
#   peak   — achieve score >= threshold on any song at given level
#   aaa    — achieve AAA (990k+) on N songs at given level
#   pfc    — achieve PFC lamp on N songs at level >= level_min
#   trial  — trial tier achievement (not in CSV export)

PLATINUM = {
    1: {
        "main": [
            {"label": "Clear 60 lv14s @ 810k+",  "type": "volume", "level": 14, "count": 60,  "score": 810_000, "exc": 12, "exc_score": 760_000},
            {"label": "960k+ on a lv14",           "type": "peak",   "level": 14, "score": 960_000},
            {"label": "Clear 10 lv15s @ 760k+",  "type": "volume", "level": 15, "count": 10,  "score": 760_000, "exc": 2,  "exc_score": None},
            {"label": "910k+ on a lv15",           "type": "peak",   "level": 15, "score": 910_000},
            {"label": "Clear a lv16",              "type": "volume", "level": 16, "count": 1,   "score": None,    "exc": 0,  "exc_score": None},
            {"label": "700k+ on a lv16",           "type": "peak",   "level": 16, "score": 700_000},
            {"label": "AAA 2 lv13s",               "type": "aaa",    "level": 13, "count": 2},
            {"label": "PFC a lv11+",               "type": "pfc",    "level_min": 11, "count": 1},
            {"label": "Gold+ on 1 Trial",          "type": "trial"},
        ],
        "subs": [
            {"label": "AAA 2 lv14s",   "type": "aaa",  "level": 14,    "count": 2},
            {"label": "960k+ a lv15",  "type": "peak", "level": 15,    "score": 960_000},
            {"label": "910k+ a lv16",  "type": "peak", "level": 16,    "score": 910_000},
            {"label": "700k+ a lv17",  "type": "peak", "level": 17,    "score": 700_000},
            {"label": "PFC a lv13+",   "type": "pfc",  "level_min": 13, "count": 1},
        ],
    },
    2: {
        "main": [
            {"label": "Clear 70 lv14s @ 820k+",  "type": "volume", "level": 14, "count": 70,  "score": 820_000, "exc": 14, "exc_score": 770_000},
            {"label": "970k+ on a lv14",           "type": "peak",   "level": 14, "score": 970_000},
            {"label": "Clear 20 lv15s @ 770k+",  "type": "volume", "level": 15, "count": 20,  "score": 770_000, "exc": 4,  "exc_score": None},
            {"label": "920k+ on a lv15",           "type": "peak",   "level": 15, "score": 920_000},
            {"label": "Clear 2 lv16s",             "type": "volume", "level": 16, "count": 2,   "score": None,    "exc": 0,  "exc_score": None},
            {"label": "750k+ on a lv16",           "type": "peak",   "level": 16, "score": 750_000},
            {"label": "AAA 5 lv13s",               "type": "aaa",    "level": 13, "count": 5},
            {"label": "PFC 3 lv11+",               "type": "pfc",    "level_min": 11, "count": 3},
            {"label": "Gold+ on 1 Trial",          "type": "trial"},
        ],
        "subs": [
            {"label": "AAA 5 lv14s",   "type": "aaa",  "level": 14,    "count": 5},
            {"label": "970k+ a lv15",  "type": "peak", "level": 15,    "score": 970_000},
            {"label": "920k+ a lv16",  "type": "peak", "level": 16,    "score": 920_000},
            {"label": "750k+ a lv17",  "type": "peak", "level": 17,    "score": 750_000},
            {"label": "PFC 2 lv13+",   "type": "pfc",  "level_min": 13, "count": 2},
        ],
    },
    3: {
        "main": [
            {"label": "Clear 80 lv14s @ 830k+",  "type": "volume", "level": 14, "count": 80,  "score": 830_000, "exc": 16, "exc_score": 780_000},
            {"label": "980k+ on a lv14",           "type": "peak",   "level": 14, "score": 980_000},
            {"label": "Clear 30 lv15s @ 780k+",  "type": "volume", "level": 15, "count": 30,  "score": 780_000, "exc": 6,  "exc_score": None},
            {"label": "930k+ on a lv15",           "type": "peak",   "level": 15, "score": 930_000},
            {"label": "Clear 3 lv16s",             "type": "volume", "level": 16, "count": 3,   "score": None,    "exc": 0,  "exc_score": None},
            {"label": "800k+ on a lv16",           "type": "peak",   "level": 16, "score": 800_000},
            {"label": "AAA 10 lv13s",              "type": "aaa",    "level": 13, "count": 10},
            {"label": "PFC a lv12+",               "type": "pfc",    "level_min": 12, "count": 1},
            {"label": "Gold+ on 2 Trials",         "type": "trial"},
        ],
        "subs": [
            {"label": "AAA 10 lv14s",  "type": "aaa",  "level": 14,    "count": 10},
            {"label": "980k+ a lv15",  "type": "peak", "level": 15,    "score": 980_000},
            {"label": "930k+ a lv16",  "type": "peak", "level": 16,    "score": 930_000},
            {"label": "800k+ a lv17",  "type": "peak", "level": 17,    "score": 800_000},
            {"label": "PFC 3 lv13+",   "type": "pfc",  "level_min": 13, "count": 3},
        ],
    },
    4: {
        "main": [
            {"label": "Clear 90 lv14s @ 840k+",  "type": "volume", "level": 14, "count": 90,  "score": 840_000, "exc": 18, "exc_score": 790_000},
            {"label": "985k+ on a lv14",           "type": "peak",   "level": 14, "score": 985_000},
            {"label": "Clear 40 lv15s @ 790k+",  "type": "volume", "level": 15, "count": 40,  "score": 790_000, "exc": 8,  "exc_score": None},
            {"label": "940k+ on a lv15",           "type": "peak",   "level": 15, "score": 940_000},
            {"label": "Clear 4 lv16s",             "type": "volume", "level": 16, "count": 4,   "score": None,    "exc": 0,  "exc_score": None},
            {"label": "850k+ on a lv16",           "type": "peak",   "level": 16, "score": 850_000},
            {"label": "AAA 15 lv13s",              "type": "aaa",    "level": 13, "count": 15},
            {"label": "PFC 2 lv12+",               "type": "pfc",    "level_min": 12, "count": 2},
            {"label": "Gold+ on 2 Trials",         "type": "trial"},
        ],
        "subs": [
            {"label": "AAA 15 lv14s",  "type": "aaa",  "level": 14,    "count": 15},
            {"label": "985k+ a lv15",  "type": "peak", "level": 15,    "score": 985_000},
            {"label": "940k+ a lv16",  "type": "peak", "level": 16,    "score": 940_000},
            {"label": "850k+ a lv17",  "type": "peak", "level": 17,    "score": 850_000},
            {"label": "PFC 4 lv13+",   "type": "pfc",  "level_min": 13, "count": 4},
        ],
    },
    5: {
        "main": [
            {"label": "Clear 100 lv14s @ 850k+", "type": "volume", "level": 14, "count": 100, "score": 850_000, "exc": 20, "exc_score": 800_000},
            {"label": "AAA a lv14",               "type": "peak",   "level": 14, "score": 990_000},
            {"label": "Clear 50 lv15s @ 800k+",  "type": "volume", "level": 15, "count": 50,  "score": 800_000, "exc": 10, "exc_score": 750_000},
            {"label": "950k+ on a lv15",           "type": "peak",   "level": 15, "score": 950_000},
            {"label": "750k+ on 5 lv16s",         "type": "volume", "level": 16, "count": 5,   "score": 750_000, "exc": 0,  "exc_score": None},
            {"label": "900k+ on a lv16",           "type": "peak",   "level": 16, "score": 900_000},
            {"label": "AAA 20 lv13s",              "type": "aaa",    "level": 13, "count": 20},
            {"label": "PFC 5 lv12+",               "type": "pfc",    "level_min": 12, "count": 5},
            {"label": "Platinum+ on 1 Trial",      "type": "trial"},
        ],
        "subs": [
            {"label": "AAA 20 lv14s",  "type": "aaa",  "level": 14,    "count": 20},
            {"label": "AAA a lv15",    "type": "peak", "level": 15,    "score": 990_000},
            {"label": "950k+ a lv16",  "type": "peak", "level": 16,    "score": 950_000},
            {"label": "900k+ a lv17",  "type": "peak", "level": 17,    "score": 900_000},
            {"label": "PFC 5 lv13+",   "type": "pfc",  "level_min": 13, "count": 5},
        ],
    },
}

# ── Data loading ─────────────────────────────────────────────────────────────────

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
        level       = req["level"]
        count       = req["count"]
        score_thresh = req.get("score")
        exc         = req.get("exc", 0)
        exc_score   = req.get("exc_score")

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
        met = effective >= count
        detail = f"{len(main)} main + {used_exc} exc" if used_exc > 0 else ""
        return met, f"{effective}/{count}", detail

    elif t == "peak":
        level       = req["level"]
        score_thresh = req["score"]
        lvl_songs   = [s for s in songs if s["level"] == level]
        if not lvl_songs:
            return False, "–", f"no lv{level} scores"
        best = max(lvl_songs, key=lambda s: s["score"])
        met  = best["score"] >= score_thresh
        gap  = f"  (need +{score_thresh - best['score']:,})" if not met else " ✓"
        detail = best["name"] if not met else ""
        return met, f"{best['score']:,}{gap}", detail

    elif t == "aaa":
        level    = req["level"]
        count    = req["count"]
        aaa_list = [s for s in songs if s["level"] == level and s["score"] >= AAA_SCORE]
        n        = len(aaa_list)
        met      = n >= count
        lvl_songs = [s for s in songs if s["level"] == level]
        if lvl_songs and not met:
            best   = max(lvl_songs, key=lambda s: s["score"])
            detail = f"best: {best['score']:,}  (need +{AAA_SCORE - best['score']:,})"
        else:
            detail = ""
        return met, f"{n}/{count}", detail

    elif t == "pfc":
        level_min = req["level_min"]
        count     = req["count"]
        pfcs      = [s for s in songs if s["level"] >= level_min and s["lamp"] == "PFC"]
        n         = len(pfcs)
        met       = n >= count
        if not met:
            near = [s for s in songs if s["level"] >= level_min and s["lamp"] in ("MFC", "GFC", "FC")]
            if near:
                best   = max(near, key=lambda s: s["score"])
                detail = f"best lamp: {best['lamp']} on {best['name']} lv{best['level']}"
            else:
                detail = "no FC lamps yet at this level"
        else:
            detail = ""
        return met, f"{n}/{count}", detail

    elif t == "trial":
        return None, "?", "not in export"

    return False, "?", ""

# ── Display ──────────────────────────────────────────────────────────────────────

ICON = {True: "✅", False: "❌", None: "❓"}

def print_level_report(level, songs):
    reqs = PLATINUM[level]["main"]
    subs = PLATINUM[level]["subs"]

    results = [evaluate(r, songs) for r in reqs]
    met_count   = sum(1 for met, _, _ in results if met is True)
    assessable  = sum(1 for met, _, _ in results if met is not None)

    print(f"\n{'─' * 62}")
    print(f"  PLATINUM {ROMAN[level]}   ({met_count}/{assessable} assessable requirements met)")
    print(f"{'─' * 62}")

    print("  Main requirements:")
    for req, (met, progress, detail) in zip(reqs, results):
        icon   = ICON[met]
        label  = req["label"]
        line   = f"    {icon}  {label:<42} {progress}"
        if detail:
            line += f"  · {detail}"
        print(line)

    print("\n  Substitutions:")
    for sub in subs:
        met, progress, detail = evaluate(sub, songs)
        icon  = ICON[met]
        label = sub["label"]
        line  = f"    {icon}  {label:<42} {progress}"
        if detail and not met:
            line += f"  · {detail}"
        print(line)

def print_summary(songs):
    print("\n" + "═" * 62)
    print("  DDR Life4 Platinum — Overview")
    print("═" * 62)
    for level in range(1, 6):
        reqs    = PLATINUM[level]["main"]
        results = [evaluate(r, songs) for r in reqs]
        met     = sum(1 for m, _, _ in results if m is True)
        total   = sum(1 for m, _, _ in results if m is not None)
        icon    = "✅" if met == total else ("🔶" if met > 0 else "❌")
        print(f"  {icon}  Platinum {ROMAN[level]:<5}  {met}/{total} met  (Trials excluded)")

# ── Main ─────────────────────────────────────────────────────────────────────────

def main():
    csv_path     = None
    target_level = None

    for arg in sys.argv[1:]:
        if arg.isdigit() and 1 <= int(arg) <= 5:
            target_level = int(arg)
        elif Path(arg).exists():
            csv_path = arg
        else:
            print(f"Warning: '{arg}' not recognized (expected a CSV path or level 1–5)")

    if csv_path is None:
        candidates = sorted(Path(".").glob("scores*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("Error: no scores CSV found. Pass the file path as an argument.")
            sys.exit(1)
        csv_path = candidates[0]
        print(f"Using: {csv_path}")

    songs = load_scores(csv_path)
    print(f"Loaded {len(songs)} score entries.\n")

    if target_level:
        print_level_report(target_level, songs)
    else:
        print_summary(songs)
        for level in range(1, 6):
            print_level_report(level, songs)

    print()

if __name__ == "__main__":
    main()
