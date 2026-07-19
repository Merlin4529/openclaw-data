# openclaw-data

Repositorio de datos del sistema OpenClaw (HARPO / TANGO). Contiene los CSV
crudos de FootyStats, las salidas procesadas de HARPO y el registro de apuestas.

**Repo publico a proposito**: los datos son de terceros, no confidenciales, y
el repo debe ser legible sin autenticacion para que Claude pueda leerlo via
`raw.githubusercontent.com`.

> **Nunca commitear credenciales.** API key de FootyStats, refresh token de
> OAuth y key de NewsData.io van en variables de entorno de Railway o en un
> `.env` local (ya ignorado por `.gitignore`).

---

## Estructura

```
raw/            CSV tal como los exporta FootyStats, sin tocar
  argentina/2026-clausura/{matches,teams,league,players}.csv
  premier/2026-27/{matches,teams,league}.csv
  laliga/2026-27/{matches,teams,league}.csv

processed/      Salidas de HARPO (probabilidades, odds devigadas, edge)
  base_argentina.csv

bets/           Registro de apuestas
  open.csv      apuestas vivas
  settled.csv   historico con resultado y pnl

scripts/
  build_manifest.py   regenera manifest.json
  load.py             loader para leer el repo desde una sesion

manifest.json   indice: que datasets hay, cuantas filas, si tienen odds/xG
```

## manifest.json

Es la entrada al repo. Describe cada dataset sin necesidad de descargarlo:
filas, completos vs incompletos, rango de fechas, jornadas, si tiene odds,
si tiene xG pre-match, y cuantas filas son realmente utilizables para backtest
(`backtestable_rows` = completas + con odds + con xG).

Regenerar despues de cualquier cambio en `raw/` o `processed/`:

```bash
python3 scripts/build_manifest.py
```

## Uso desde una sesion de Claude

Pasarle la URL base del repo. Despues:

```python
import urllib.request, json, io, pandas as pd
BASE = "https://raw.githubusercontent.com/USUARIO/openclaw-data/main/"
m = json.loads(urllib.request.urlopen(BASE + "manifest.json").read())
df = pd.read_csv(io.BytesIO(urllib.request.urlopen(BASE + m["datasets"]["argentina_2026-clausura_matches"]["path"]).read()))
```

O con el loader incluido (`scripts/load.py`, editar la constante `REPO`).

## Estado de los datos (19 jul 2026)

| Liga | Completos | Odds | xG | Backtesteable |
|---|---|---|---|---|
| Argentina Clausura 2026 | 255 | si | si | **240** |
| Premier 2026-27 | 0 | no | no | 0 |
| La Liga 2026-27 | 0 | no | no | 0 |

Premier y La Liga solo tienen el fixture de la temporada que arranca en agosto.
Para poder backtestear hace falta descargar de FootyStats la temporada
**2025-26** de cada una (completa, con odds y xG) y guardarla en
`raw/premier/2025-26/` y `raw/laliga/2025-26/`.

## Convenciones

- Nombres de archivo normalizados: `matches.csv`, `teams.csv`, `league.csv`,
  `players.csv`. El nombre largo de FootyStats se descarta.
- Una carpeta por temporada, formato `YYYY-YY` o `YYYY-torneo`.
- Los CSV de `raw/` no se editan nunca. Toda transformacion va a `processed/`.
- Commits de datos con mensaje `data: <liga> <temporada> <fecha>`.
