#!/usr/bin/env python3
"""OpenClaw Daily Pipeline - Railway Cron Job"""

import os
import subprocess
from datetime import datetime
from pathlib import Path

REPO_PATH = Path.cwd()
FOOTYSTATS_API_KEY = os.getenv('FOOTYSTATS_API_KEY')
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_REPO = os.getenv('GITHUB_REPO', 'Merlin4529/openclaw-data')

def log(msg):
    print(f"[{datetime.now().isoformat()}] {msg}")

def main():
    log("OpenClaw Pipeline - INICIO")
    
    try:
        # Ejecutar scripts
        scripts = [
            'scripts/build_manifest.py',
            'scripts/harpo_v3_modulator.py',
            'scripts/d2_autonomy_protocol.py',
            'scripts/joker_selection_logic.py',
        ]
        
        for script in scripts:
            script_path = REPO_PATH / script
            if script_path.exists():
                log(f"Ejecutando {script}")
                result = subprocess.run(['python3', str(script_path)], cwd=REPO_PATH)
                if result.returncode != 0:
                    log(f"Error en {script}")
            else:
                log(f"Script no encontrado: {script}")
        
        # Git commit + push
        os.chdir(REPO_PATH)
        subprocess.run(['git', 'config', 'user.email', 'openclaw@railway.io'], capture_output=True)
        subprocess.run(['git', 'config', 'user.name', 'OpenClaw Railway'], capture_output=True)
        
        # Verificar cambios
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        
        if result.stdout.strip():
            log("Hay cambios, commiteando...")
            subprocess.run(['git', 'add', '-A'], capture_output=True)
            
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            subprocess.run(['git', 'commit', '-m', f'[AUTO-RAILWAY] Pipeline {timestamp}'], capture_output=True)
            
            # Push con token
            remote_url = f"https://oauth2:{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
            subprocess.run(['git', 'push', remote_url, 'main'], capture_output=True)
            
            log("Push completado")
        else:
            log("Sin cambios para commitear")
        
        log("Pipeline COMPLETADO")
        return 0
    
    except Exception as e:
        log(f"Error: {e}")
        return 1

if __name__ == '__main__':
    exit(main())
