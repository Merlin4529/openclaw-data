#!/usr/bin/env python3
"""
Congela las predicciones de una jornada en un snapshot inmutable.

    python scripts/snapshot.py --liga argentina --jornada 1

Escribe predictions/<liga>/<temporada>-j<NN>.csv con TODAS las predicciones
de la jornada (no solo las apostadas). Ese archivo es el registro historico:
se escribe una sola vez, antes de que se jueguen los partidos, y despues solo
lo toca close_jornada.py para agregar los resultados.

Por que el universo completo y no solo las picks:
  La calibracion se estima sobre todas las predicciones generadas. Guardando
  solo las 3 apostadas, en 8 jornadas hay n=24. Guardando las 15, n=120.
  Es la diferencia entre poder calibrar y no poder.

Por que congelar las cuotas:
  Se mueven entre el miercoles y el sabado. Si el EV se recalcula despues con
  cuotas distintas, el analisis queda contaminado. La cuota que se guarda es
  la que estaba al momento de decidir.
"""
import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import harpo  # noqa: E402

TEMPORADAS = {
    "argentina": "2026-clausura",
    "premier": "2026-27",
    "laliga": "2026-27",
}

COLS = [
    "snapshot_utc", "liga", "temporada", "jornada", "fecha",
    "local", "visitante",
    "lambda_h", "lambda_a", "pH", "pD", "pA", "p1X", "pX2", "pO25",
    "o1", "ox", "o2", "o1X", "i1X",
    "EV_1X", "EV_home",
    "seleccionada", "stake", "mercado", "K_home", "K_away", "modelo",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--liga", default="argentina", choices=list(TEMPORADAS))
    ap.add_argument("--jornada", type=int, required=True)
    ap.add_argument("--force", action="store_true",
                    help="sobrescribe un snapshot existente (romper solo a proposito)")
    args = ap.parse_args()

    temporada = TEMPORADAS[args.liga]
    dest = os.path.join(ROOT, "predictions", args.liga,
                        f"{temporada}-j{args.jornada:02d}.csv")

    if os.path.exists(dest) and not args.force:
        sys.exit(f"ERROR: {dest} ya existe.\n"
                 "El snapshot es inmutable por diseno. Si de verdad hay que "
                 "regenerarlo, usar --force y dejar constancia en el commit.")

    state = harpo.load_state()
    matches = pd.read_csv(os.path.join(
        ROOT, "raw", args.liga, temporada, "matches.csv"))

    pred = harpo.predict(matches, state)
    j = pred[(pred.gw == args.jornada) & (pred.status == "incomplete")].copy()
    if j.empty:
        sys.exit(f"ERROR: no hay partidos incompletos en la jornada {args.jornada}.")
    if "EV_1X" not in j.columns or j.EV_1X.isna().all():
        sys.exit("ERROR: la jornada no tiene cuotas. Sin cuotas no hay EV ni snapshot util.")

    sel = harpo.select_bets(pred[pred.gw == args.jornada], state)
    stakes = {(r.local, r.visitante): r.stake for r in sel.itertuples()}

    cal = state["calibracion_xg"]
    j["snapshot_utc"] = pd.Timestamp.now("UTC").isoformat(timespec="seconds")
    j["liga"] = args.liga
    j["temporada"] = temporada
    j["jornada"] = args.jornada
    j["stake"] = [stakes.get((r.local, r.visitante), 0) for r in j.itertuples()]
    j["seleccionada"] = j.stake > 0
    j["mercado"] = "1X"
    j["K_home"] = cal["K_home"]
    j["K_away"] = cal["K_away"]
    j["modelo"] = state["version"]

    for c in COLS:
        if c not in j.columns:
            j[c] = pd.NA

    j = j[COLS].sort_values("EV_1X", ascending=False)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    num = j.select_dtypes("number").columns
    j[num] = j[num].round(4)
    j.to_csv(dest, index=False)

    print(f"Snapshot escrito: {os.path.relpath(dest, ROOT)}")
    print(f"  {len(j)} predicciones | {int(j.seleccionada.sum())} seleccionadas "
          f"| stake total {int(j.stake.sum())}")
    print()
    print(j[["local", "visitante", "p1X", "o1X", "EV_1X", "stake"]]
          .head(8).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
