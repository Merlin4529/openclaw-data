#!/usr/bin/env python3
"""
Loader de OpenClaw. Lee el manifest y los datasets directamente desde
raw.githubusercontent.com, sin necesidad de clonar el repo.

Uso tipico dentro de una sesion de Claude:

    from load import manifest, load
    m = manifest()                      # que hay y que tan fresco esta
    df = load("argentina_2026-clausura_matches")

Editar REPO con el usuario/repo reales antes de usar.
"""
import io
import json
import urllib.request

# ---------------------------------------------------------------------
REPO = "USUARIO/openclaw-data"   # <-- CAMBIAR
BRANCH = "main"
# ---------------------------------------------------------------------

BASE = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"

_cache = {}


def _get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def manifest(refresh=False):
    """Devuelve el manifest.json del repo como dict."""
    if refresh or "manifest" not in _cache:
        _cache["manifest"] = json.loads(_get(BASE + "manifest.json"))
    return _cache["manifest"]


def datasets():
    """Lista las claves disponibles con un resumen de una linea."""
    m = manifest()
    for k, v in m["datasets"].items():
        bits = [f"rows={v.get('rows')}"]
        if "complete" in v:
            bits.append(f"complete={v['complete']}")
        if "backtestable_rows" in v:
            bits.append(f"backtestable={v['backtestable_rows']}")
        print(f"{k:40s} {' '.join(bits)}")


def load(key):
    """Carga un dataset por clave del manifest y lo devuelve como DataFrame."""
    import pandas as pd
    m = manifest()
    if key not in m["datasets"]:
        raise KeyError(f"'{key}' no esta en el manifest. "
                       f"Disponibles: {list(m['datasets'])}")
    path = m["datasets"][key]["path"]
    raw = _get(BASE + path)
    return pd.read_csv(io.BytesIO(raw))


def load_path(path):
    """Carga por ruta relativa directa, sin pasar por el manifest."""
    import pandas as pd
    return pd.read_csv(io.BytesIO(_get(BASE + path)))


if __name__ == "__main__":
    m = manifest()
    print(f"manifest actualizado: {m['updated_utc']}\n")
    datasets()
