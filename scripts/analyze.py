#!/usr/bin/env python3
"""
Analisis acumulado sobre todos los snapshots cerrados.

    python scripts/analyze.py --liga argentina

Concatena predictions/<liga>/*.csv y evalua tendencias sobre el universo
completo de predicciones (no solo las apostadas), que es lo que da n
suficiente para calibrar.

Reporta:
  - calibracion por bucket de p1X (predicho vs real)
  - Brier score y accuracy por jornada (deriva del modelo)
  - deriva del K: el K vigente vs el que sugieren los partidos ya jugados
  - ROI acumulado y por banda de EV
"""
import argparse
import glob
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def cargar(liga):
    paths = sorted(glob.glob(os.path.join(ROOT, "predictions", liga, "*.csv")))
    if not paths:
        raise SystemExit(f"No hay snapshots en predictions/{liga}/")
    df = pd.concat([pd.read_csv(p) for p in paths], ignore_index=True)
    cerrados = df[df.get("res").notna()] if "res" in df.columns else df.iloc[:0]
    return df, cerrados


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--liga", default="argentina")
    args = ap.parse_args()

    todo, c = cargar(args.liga)
    print(f"Snapshots: {todo.jornada.nunique()} jornadas | "
          f"{len(todo)} predicciones | {len(c)} cerradas\n")

    if c.empty:
        print("Todavia no hay jornadas cerradas. Correr close_jornada.py "
              "despues de que se jueguen los partidos.")
        return

    # ---- calibracion 1X sobre universo completo ----
    print("=== CALIBRACION 1X (universo completo) ===")
    print(f"{'bucket':>14}  {'n':>4}  {'pred':>6}  {'real':>6}  {'gap':>6}")
    for lo, hi in [(0.0, 0.60), (0.60, 0.65), (0.65, 0.70),
                   (0.70, 0.75), (0.75, 0.80), (0.80, 1.01)]:
        s = c[(c.p1X >= lo) & (c.p1X < hi)]
        if len(s) >= 5:
            pred, real = s.p1X.mean() * 100, s.hit_1X.mean() * 100
            flag = "  <-- n bajo" if len(s) < 30 else ""
            print(f"  {lo:.2f}-{hi:.2f}  {len(s):4d}  {pred:5.1f}%  "
                  f"{real:5.1f}%  {real-pred:+5.1f}{flag}")
    print("\n(n>=30 por bucket para dejar de ser PROVISIONAL)")

    # ---- evolucion por jornada ----
    print("\n=== POR JORNADA ===")
    print(f"{'jor':>4}  {'n':>3}  {'acc':>6}  {'Brier':>6}  {'1X real':>8}  "
          f"{'stake':>6}  {'pnl':>8}  {'ROI':>7}")
    for jj, g in c.groupby("jornada"):
        oh = pd.get_dummies(g.res).reindex(columns=["H", "D", "A"], fill_value=0)
        brier = ((g[["pH", "pD", "pA"]].values - oh.values) ** 2).sum(axis=1).mean()
        ap_ = g[g.stake > 0]
        stake, pnl = ap_.stake.sum(), ap_.pnl.sum()
        roi = f"{pnl/stake*100:+6.1f}%" if stake else "     -"
        print(f"  {int(jj):2d}  {len(g):3d}  {g.hit_argmax.mean()*100:5.1f}%  "
              f"{brier:.4f}  {g.hit_1X.mean()*100:7.1f}%  {stake:6.0f}  "
              f"{pnl:+8.2f}  {roi}")

    # ---- acumulado de apuestas ----
    ap_ = c[c.stake > 0]
    if len(ap_):
        stake, pnl = ap_.stake.sum(), ap_.pnl.sum()
        print(f"\n=== APUESTAS ACUMULADO ===")
        print(f"  picks: {len(ap_)} | aciertos: {int(ap_.hit_1X.sum())} "
              f"({ap_.hit_1X.mean()*100:.1f}%)")
        print(f"  stake: {stake:.0f} | pnl: {pnl:+.2f} | ROI: {pnl/stake*100:+.1f}%")
        print(f"  EV medio predicho: {ap_.EV_1X.mean()*100:+.1f}%")
        print("\n  Por banda de EV:")
        for lo, hi, lab in [(0.10, 0.15, "0.10-0.15"), (0.15, 0.20, "0.15-0.20"),
                            (0.20, 9, ">0.20")]:
            s = ap_[(ap_.EV_1X >= lo) & (ap_.EV_1X < hi)]
            if len(s):
                print(f"    {lab:>10}  n={len(s):2d}  acc={s.hit_1X.mean()*100:5.1f}%  "
                      f"ROI={s.pnl.sum()/s.stake.sum()*100:+6.1f}%")
        if len(ap_) < 30:
            print(f"\n  AVISO: n={len(ap_)}. Con menos de ~100 picks no se puede "
                  "distinguir habilidad de suerte. Estos numeros son ruido.")

    # ---- deriva del K ----
    print("\n=== DERIVA DEL K ===")
    with open(os.path.join(ROOT, "state.json"), encoding="utf-8") as f:
        st = json.load(f)
    kh_v, ka_v = st["calibracion_xg"]["K_home"], st["calibracion_xg"]["K_away"]
    print(f"  vigente en state.json:  K_home={kh_v:.4f}  K_away={ka_v:.4f}")

    mp = os.path.join(ROOT, "raw", args.liga,
                      st.get("temporada", "2026-clausura"), "matches.csv")
    mp = mp if os.path.exists(mp) else os.path.join(
        ROOT, "raw", args.liga, "2026-clausura", "matches.csv")
    if os.path.exists(mp):
        m = pd.read_csv(mp).rename(columns={
            "Home Team Pre-Match xG": "hxg", "Away Team Pre-Match xG": "axg"})
        cm = m[(m.status == "complete") & (m.hxg > 0) & (m.axg > 0)]
        if len(cm) >= 30:
            kh = cm.home_team_goal_count.mean() / cm.hxg.mean()
            ka = cm.away_team_goal_count.mean() / cm.axg.mean()
            print(f"  sugerido (n={len(cm)}):      K_home={kh:.4f}  K_away={ka:.4f}")
            dh, da = abs(kh - kh_v) / kh_v, abs(ka - ka_v) / ka_v
            if max(dh, da) > 0.10:
                print(f"  >>> deriva {max(dh,da)*100:.0f}% — evaluar recalibrar")
            else:
                print(f"  deriva {max(dh,da)*100:.0f}% — dentro de tolerancia")
        else:
            print(f"  n={len(cm)} insuficiente para sugerir K (minimo 30)")

    print("\nRegla: un solo parametro modificado por jornada. Si cambian pesos "
          "y umbrales a la vez, no se sabe que causo que.")


if __name__ == "__main__":
    main()
