#!/usr/bin/env python3
"""
Cierra una jornada: agrega resultados y pnl al snapshot ya congelado.

    python scripts/close_jornada.py --liga argentina --jornada 1

Requiere que matches.csv ya tenga los partidos de esa jornada en status
'complete'. Agrega al snapshot las columnas de resultado SIN tocar ninguna
de las columnas de prediccion: lo que se predijo queda como se predijo.

Tambien imprime el reporte de calibracion y ROI de la jornada, y mueve
las picks de bets/open.csv a bets/settled.csv.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TEMPORADAS = {
    "argentina": "2026-clausura",
    "premier": "2026-27",
    "laliga": "2026-27",
}

RES_COLS = ["goles_h", "goles_a", "res", "hit_1X", "hit_argmax", "pnl", "cerrado_utc"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--liga", default="argentina", choices=list(TEMPORADAS))
    ap.add_argument("--jornada", type=int, required=True)
    args = ap.parse_args()

    temporada = TEMPORADAS[args.liga]
    snap_path = os.path.join(ROOT, "predictions", args.liga,
                             f"{temporada}-j{args.jornada:02d}.csv")
    if not os.path.exists(snap_path):
        sys.exit(f"ERROR: no existe {snap_path}. Correr snapshot.py antes de la jornada.")

    snap = pd.read_csv(snap_path)
    if "res" in snap.columns and snap.res.notna().any():
        sys.exit("ERROR: esta jornada ya fue cerrada.")

    matches = pd.read_csv(os.path.join(
        ROOT, "raw", args.liga, temporada, "matches.csv"))
    m = matches[(matches["Game Week"] == args.jornada) &
                (matches.status == "complete")]
    if m.empty:
        sys.exit(f"ERROR: la jornada {args.jornada} no tiene partidos completos "
                 "en matches.csv. Actualizar el CSV desde FootyStats primero.")

    goles = {(r.home_team_name, r.away_team_name):
             (r.home_team_goal_count, r.away_team_goal_count)
             for r in m.itertuples()}

    gh, ga = [], []
    for r in snap.itertuples():
        g = goles.get((r.local, r.visitante), (np.nan, np.nan))
        gh.append(g[0])
        ga.append(g[1])
    snap["goles_h"], snap["goles_a"] = gh, ga

    falt = snap.goles_h.isna().sum()
    if falt:
        print(f"AVISO: {falt} partidos sin resultado (postergados?), quedan sin cerrar.")

    jugado = snap.goles_h.notna()
    snap["res"] = pd.Series(pd.NA, index=snap.index, dtype="object")
    snap.loc[jugado, "res"] = np.where(
        snap.loc[jugado, "goles_h"] > snap.loc[jugado, "goles_a"], "H",
        np.where(snap.loc[jugado, "goles_h"] == snap.loc[jugado, "goles_a"],
                 "D", "A"))
    argmax = snap[["pH", "pD", "pA"]].idxmax(axis=1).str[1]
    snap["hit_1X"] = pd.Series(pd.NA, index=snap.index, dtype="Float64")
    snap["hit_argmax"] = pd.Series(pd.NA, index=snap.index, dtype="Float64")
    snap.loc[jugado, "hit_1X"] = (snap.loc[jugado, "res"] != "A").astype(float)
    snap.loc[jugado, "hit_argmax"] = (
        argmax[jugado] == snap.loc[jugado, "res"]).astype(float)
    snap["pnl"] = np.where(
        (snap.stake > 0) & snap.res.notna(),
        np.where(snap.hit_1X == 1, snap.stake * (snap.o1X - 1), -snap.stake), 0.0)
    snap["cerrado_utc"] = pd.Timestamp.now("UTC").isoformat(timespec="seconds")

    num = snap.select_dtypes("number").columns
    snap[num] = snap[num].round(4)
    snap.to_csv(snap_path, index=False)

    jugados = snap[snap.res.notna()]
    apostadas = jugados[jugados.stake > 0]

    print(f"=== CIERRE JORNADA {args.jornada} - {args.liga.upper()} ===\n")
    print(f"Partidos cerrados: {len(jugados)}/{len(snap)}")
    print(f"Accuracy argmax (universo): {jugados.hit_argmax.mean()*100:.1f}%")
    print(f"1X acierta (universo): {jugados.hit_1X.mean()*100:.1f}%")
    print(f"  predicho medio p1X: {jugados.p1X.mean()*100:.1f}%")
    print(f"Distribucion real: " +
          " ".join(f"{k}={v}" for k, v in jugados.res.value_counts().items()))

    if len(apostadas):
        stake = apostadas.stake.sum()
        pnl = apostadas.pnl.sum()
        print(f"\n--- APUESTAS ---")
        print(apostadas[["local", "visitante", "o1X", "stake", "res", "hit_1X", "pnl"]]
              .to_string(index=False))
        print(f"\nStake: {stake:.0f} | PnL: {pnl:+.2f} | ROI: {pnl/stake*100:+.1f}%")
        print(f"Aciertos: {int(apostadas.hit_1X.sum())}/{len(apostadas)}")

        # actualizar settled.csv
        settled_path = os.path.join(ROOT, "bets", "settled.csv")
        open_path = os.path.join(ROOT, "bets", "open.csv")
        if os.path.exists(open_path):
            op = pd.read_csv(open_path)
            if len(op):
                key = apostadas.set_index(["local", "visitante"])
                op["resultado"] = [
                    key.res.get((r.local, r.visitante), "") for r in op.itertuples()]
                op["pnl"] = [
                    key.pnl.get((r.local, r.visitante), 0) for r in op.itertuples()]
                hdr = not os.path.exists(settled_path) or \
                    os.path.getsize(settled_path) < 50
                op.to_csv(settled_path, mode="a", header=hdr, index=False)
                pd.DataFrame(columns=op.columns).to_csv(open_path, index=False)
                print(f"\n{len(op)} picks movidas a bets/settled.csv")

        print("\nRECORDAR: actualizar bankroll.actual en state.json")

    print("\n--- CALIBRACION 1X POR BUCKET (esta jornada) ---")
    for lo, hi in [(0.0, 0.65), (0.65, 0.70), (0.70, 0.75), (0.75, 1.0)]:
        s = jugados[(jugados.p1X >= lo) & (jugados.p1X < hi)]
        if len(s):
            print(f"  p1X {lo:.2f}-{hi:.2f}  n={len(s):2d}  "
                  f"pred={s.p1X.mean()*100:.1f}%  real={s.hit_1X.mean()*100:.1f}%")
    print("\n(n de una jornada es muy chico para concluir: acumular con "
          "scripts/analyze.py sobre todos los snapshots)")


if __name__ == "__main__":
    main()
