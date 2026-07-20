#!/usr/bin/env python3
"""
HARPO v2.1 - motor de prediccion con xG calibrado.

Cambio central respecto de v2.0:
  El xG pre-match de FootyStats esta inflado. Sobre 240 partidos del
  Apertura 2026 la relacion goles_reales / xG_pre fue:
      local     1.192 / 1.386 = 0.860
      visitante 0.900 / 1.412 = 0.638
  El visitante venia inflado ~57%. Ademas v2.0 aplicaba un multiplicador
  de localia de 1.15 SOBRE ese lambda ya inflado: doble error.

  v2.1 escala por K_home / K_away y elimina el multiplicador de localia
  (el sesgo de local ya queda contenido en la asimetria de los K).

Efecto medido (n=240):
  Over 2.5 predicho   57.2%  ->  34.8%   (real 34.2%)
  Predicciones empate     0  ->  10
  Prob. media empate  25.1%  ->  30.9%   (real 31.2%)
  Brier              0.6625  -> 0.6536

Nota honesta: la accuracy 1X2 queda en ~41%, por debajo del mercado
(42.9%). HARPO no predice mejor que la casa. Lo que aporta es una
probabilidad CALIBRADA, que es lo que permite detectar cuando la cuota
esta mal puesta. El edge viene de la calibracion, no de la prediccion.
"""
import json
import os
import numpy as np
import pandas as pd
from scipy.stats import poisson

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

RHO = -0.05          # Dixon-Coles: correccion de scorelines bajos
MAX_GOLES = 9        # dimension de la matriz de scorelines
XG_MIN = 0.3         # piso para evitar lambdas degenerados


def load_state(path=None):
    path = path or os.path.join(ROOT, "state.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _dc(i, j, lh, la, rho):
    """Factor de correccion Dixon-Coles para scorelines bajos."""
    if i == 0 and j == 0:
        return 1 - lh * la * rho
    if i == 0 and j == 1:
        return 1 + lh * rho
    if i == 1 and j == 0:
        return 1 + la * rho
    if i == 1 and j == 1:
        return 1 - rho
    return 1.0


def score_matrix(lh, la, n=MAX_GOLES, rho=RHO):
    """Matriz de probabilidad de scorelines (i goles local, j visitante)."""
    M = np.array([[poisson.pmf(i, lh) * poisson.pmf(j, la) * _dc(i, j, lh, la, rho)
                   for j in range(n)] for i in range(n)])
    return M / M.sum()


def outcome_probs(lh, la):
    """Devuelve (pH, pD, pA, pOver25) a partir de los lambdas."""
    M = score_matrix(lh, la)
    pH = np.tril(M, -1).sum()
    pD = float(np.trace(M))
    pA = np.triu(M, 1).sum()
    n = M.shape[0]
    pO25 = 1 - sum(M[i, j] for i in range(n) for j in range(n) if i + j <= 2)
    return pH, pD, pA, pO25


def lambdas(hxg, axg, k_home, k_away):
    """Aplica la calibracion K al xG pre-match. Sin multiplicador de localia."""
    return max(hxg, XG_MIN) * k_home, max(axg, XG_MIN) * k_away


def devig(o1, ox, o2):
    """Probabilidades implicitas del mercado, normalizadas (proporcional)."""
    if min(o1, ox, o2) <= 0:
        return None
    inv = np.array([1 / o1, 1 / ox, 1 / o2])
    return inv / inv.sum()


def predict(df, state):
    """
    df: matches.csv de FootyStats (columnas originales).
    Devuelve DataFrame con probabilidades, cuotas devigadas y EV por mercado.
    """
    cal = state["calibracion_xg"]
    kh, ka = cal["K_home"], cal["K_away"]

    d = df.rename(columns={
        "Home Team Pre-Match xG": "hxg",
        "Away Team Pre-Match xG": "axg",
        "Game Week": "gw",
    }).copy()
    d["fecha"] = pd.to_datetime(
        d["date_GMT"].str.replace(" - ", " ", regex=False),
        format="%b %d %Y %I:%M%p", errors="coerce")

    out = []
    for _, r in d.iterrows():
        if r.hxg <= 0 or r.axg <= 0:
            continue
        lh, la = lambdas(r.hxg, r.axg, kh, ka)
        pH, pD, pA, pO25 = outcome_probs(lh, la)

        row = dict(fecha=r["fecha"], gw=r.gw, status=r.status,
                   local=r.home_team_name, visitante=r.away_team_name,
                   lambda_h=round(lh, 3), lambda_a=round(la, 3),
                   pH=pH, pD=pD, pA=pA, p1X=pH + pD, pX2=pD + pA, pO25=pO25)

        o1, ox, o2 = (r.odds_ft_home_team_win, r.odds_ft_draw,
                      r.odds_ft_away_team_win)
        imp = devig(o1, ox, o2)
        if imp is not None:
            o1X = 1 / (1 / o1 + 1 / ox)
            row.update(o1=o1, ox=ox, o2=o2, o1X=round(o1X, 3),
                       i1X=imp[0] + imp[1],
                       EV_1X=(pH + pD) * o1X - 1,
                       EV_home=pH * o1 - 1)
        out.append(row)

    return pd.DataFrame(out)


def select_bets(pred, state):
    """
    Aplica los filtros de state.json: mercados habilitados, EV minimo,
    tope de picks y de exposicion. Devuelve las picks con su stake.
    """
    u = state["umbrales"]
    st = state["stakes"]
    ev_min = u["EV_minimo_argentina"]

    cand = pred[(pred.status == "incomplete") & (pred.EV_1X > ev_min)].copy()
    cand = cand.sort_values("EV_1X", ascending=False).head(u["max_picks_jornada"])

    def stake_for(ev):
        if ev > 0.15:
            return st["EV>0.15"]
        if ev >= 0.10:
            return st["EV_0.10_0.15"]
        return 0

    cand["stake"] = cand.EV_1X.map(stake_for)
    cand = cand[cand.stake > 0]

    # tope de exposicion
    tope = state["bankroll"]["actual"] * u["max_exposicion_jornada_pct"]
    if cand.stake.sum() > tope:
        cand = cand.iloc[:0]  # mejor no apostar que violar el tope
    return cand


def calibrate_k(df):
    """
    Recalcula K_home / K_away sobre los partidos completos de df.
    Correr despues de cada jornada; NO aplicar automaticamente,
    revisar contra el K vigente antes de actualizar state.json.
    """
    d = df.rename(columns={"Home Team Pre-Match xG": "hxg",
                           "Away Team Pre-Match xG": "axg"})
    c = d[(d.status == "complete") & (d.hxg > 0) & (d.axg > 0)]
    if len(c) < 30:
        raise ValueError(f"n={len(c)} insuficiente para recalibrar (minimo 30)")
    return dict(
        K_home=round(c.home_team_goal_count.mean() / c.hxg.mean(), 4),
        K_away=round(c.away_team_goal_count.mean() / c.axg.mean(), 4),
        n=int(len(c)),
    )


if __name__ == "__main__":
    state = load_state()
    matches = pd.read_csv(os.path.join(
        ROOT, "raw", "argentina", "2026-clausura", "matches.csv"))
    pred = predict(matches, state)
    j1 = pred[(pred.status == "incomplete") & (pred.gw == 1)]
    cols = ["local", "visitante", "pH", "pD", "p1X", "o1X", "EV_1X"]
    print(j1[cols].sort_values("EV_1X", ascending=False).round(3).to_string(index=False))
    print("\nPICKS SELECCIONADAS:")
    sel = select_bets(pred[pred.gw == 1], state)
    print(sel[["local", "visitante", "o1X", "EV_1X", "stake"]].round(3).to_string(index=False))
