#!/usr/bin/env python3
"""Detectar patrones y tendencias en históricos - Para mejorar HARPO"""

import csv
from pathlib import Path
from collections import defaultdict

PROCESSED_PATH = Path("processed")
OUTPUT_PATH = Path("predictions")
OUTPUT_PATH.mkdir(exist_ok=True)

def analizar_historicos():
    """Lee históricos y detecta patrones"""
    
    historicos = PROCESSED_PATH / "historicos_acumulativos.csv"
    
    equipos_stats = defaultdict(lambda: {
        "partidos": 0,
        "goles_favor": 0,
        "goles_contra": 0,
        "victorias": 0,
        "derrotas": 0,
        "empates": 0,
        "xg_promedio": 0.0,
    })
    
    # Leer CSV
    with open(historicos, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                local = row.get('home_team_name', '').strip()
                visitante = row.get('away_team_name', '').strip()
                goles_local = int(row.get('home_team_goal_count', 0) or 0)
                goles_visitante = int(row.get('away_team_goal_count', 0) or 0)
                xg_local = float(row.get('Home Team Pre-Match xG', 0) or 0)
                
                if not local or not visitante:
                    continue
                
                # Stats Local
                equipos_stats[local]["partidos"] += 1
                equipos_stats[local]["goles_favor"] += goles_local
                equipos_stats[local]["goles_contra"] += goles_visitante
                equipos_stats[local]["xg_promedio"] += xg_local
                
                if goles_local > goles_visitante:
                    equipos_stats[local]["victorias"] += 1
                elif goles_local < goles_visitante:
                    equipos_stats[local]["derrotas"] += 1
                else:
                    equipos_stats[local]["empates"] += 1
                
                # Stats Visitante
                equipos_stats[visitante]["partidos"] += 1
                equipos_stats[visitante]["goles_favor"] += goles_visitante
                equipos_stats[visitante]["goles_contra"] += goles_local
                
                if goles_visitante > goles_local:
                    equipos_stats[visitante]["victorias"] += 1
                elif goles_visitante < goles_local:
                    equipos_stats[visitante]["derrotas"] += 1
                else:
                    equipos_stats[visitante]["empates"] += 1
                    
            except (ValueError, KeyError):
                continue
    
    # Normalizar xG
    for equipo in equipos_stats:
        if equipos_stats[equipo]["partidos"] > 0:
            equipos_stats[equipo]["xg_promedio"] /= equipos_stats[equipo]["partidos"]
    
    # Guardar patrones
    with open(OUTPUT_PATH / "patrones_detectados.json", 'w', encoding='utf-8') as f:
        import json
        json.dump(dict(equipos_stats), f, indent=2, ensure_ascii=False)
    
    print(f"✅ {len(equipos_stats)} equipos analizados")
    print(f"✅ Patrones guardados en predictions/patrones_detectados.json")

if __name__ == '__main__':
    analizar_historicos()
