#!/usr/bin/env python3
"""
Genera manifest.json describiendo el estado de cada dataset del repo.
Uso:  python3 scripts/build_manifest.py
Correr desde la raiz del repo, o dejar que el cron lo llame con cwd=repo.
"""
import json, os, glob, datetime
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATE_FMT = "%b %d %Y %I:%M%p"


def parse_dates(s):
    return pd.to_datetime(s.str.replace(" - ", " ", regex=False),
                          format=DATE_FMT, errors="coerce")


def describe_matches(path):
    df = pd.read_csv(path)
    out = {"rows": int(len(df))}

    if "status" in df.columns:
        vc = df["status"].value_counts().to_dict()
        out["complete"] = int(vc.get("complete", 0))
        out["incomplete"] = int(vc.get("incomplete", 0))

    if "date_GMT" in df.columns:
        d = parse_dates(df["date_GMT"])
        if d.notna().any():
            out["date_min"] = str(d.min().date())
            out["date_max"] = str(d.max().date())

    if "Game Week" in df.columns:
        gw = pd.to_numeric(df["Game Week"], errors="coerce")
        out["gw_min"] = None if gw.isna().all() else int(gw.min())
        out["gw_max"] = None if gw.isna().all() else int(gw.max())

    oc = "odds_ft_home_team_win"
    if oc in df.columns:
        odds = pd.to_numeric(df[oc], errors="coerce").fillna(0)
        out["rows_with_odds"] = int((odds > 0).sum())
        out["has_odds"] = bool((odds > 0).any())
        if "Game Week" in df.columns and out["has_odds"]:
            gw = pd.to_numeric(df["Game Week"], errors="coerce")
            out["last_gw_with_odds"] = int(gw[odds > 0].max())

    xc = "Home Team Pre-Match xG"
    if xc in df.columns:
        xg = pd.to_numeric(df[xc], errors="coerce").fillna(0)
        out["rows_with_xg"] = int((xg > 0).sum())
        out["has_xg"] = bool((xg > 0).any())

    # utilidad para backtest: completos que ademas tienen odds y xg
    if {"status", oc, xc}.issubset(df.columns):
        odds = pd.to_numeric(df[oc], errors="coerce").fillna(0)
        xg = pd.to_numeric(df[xc], errors="coerce").fillna(0)
        usable = (df["status"] == "complete") & (odds > 0) & (xg > 0)
        out["backtestable_rows"] = int(usable.sum())

    return out


def describe_generic(path):
    df = pd.read_csv(path)
    out = {"rows": int(len(df)), "cols": int(len(df.columns))}
    if "matches_played" in df.columns:
        out["matches_played_sum"] = int(
            pd.to_numeric(df["matches_played"], errors="coerce").fillna(0).sum())
    return out


def main():
    datasets = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "raw", "*", "*", "*.csv"))
                       + glob.glob(os.path.join(ROOT, "processed", "*.csv"))):
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        key = rel.replace("raw/", "").replace("processed/", "processed_") \
                 .replace(".csv", "").replace("/", "_")
        try:
            if os.path.basename(path) in ("matches.csv", "base_argentina.csv"):
                info = describe_matches(path)
            else:
                info = describe_generic(path)
        except Exception as e:
            info = {"error": str(e)}
        info["path"] = rel
        info["bytes"] = os.path.getsize(path)
        datasets[key] = info

    manifest = {
        "updated_utc": datetime.datetime.now(datetime.timezone.utc)
                        .isoformat(timespec="seconds"),
        "generator": "scripts/build_manifest.py",
        "datasets": datasets,
    }

    dest = os.path.join(ROOT, "manifest.json")
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"manifest.json escrito: {len(datasets)} datasets")


if __name__ == "__main__":
    main()
