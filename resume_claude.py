"""Preflight and run the user-requested Opus 5 subscription benchmark."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

from check_fable import quota
from lab import STATE,PROJECT,backup,run_cli

# Refresh the isolated copy from the current subscription login, inside vault.
destination=STATE/'claude-config/.credentials.json'
backup(destination,STATE/'backups')
shutil.copy2(Path.home()/'.claude/.credentials.json',destination)
workspace=STATE/'preflight'
record=STATE/'opus-preflight'
record.mkdir(exist_ok=True)
check=run_cli('claude','frontier',workspace,record,'Reply exactly OK. Do not use tools.',timeout=60)
if check['is_error']:
    print(check['result']);raise SystemExit(2)
subprocess.run([sys.executable,str(PROJECT/'run_benchmark.py'),'claude','--seeds','1','2'],cwd=PROJECT,check=True)
