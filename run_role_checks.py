"""Availability probe followed by a separately labelled delegation comparison."""
import argparse
import json
import subprocess
from benchmarks import create
from lab import PROJECT, STATE, dump, run_cli

p=argparse.ArgumentParser();p.add_argument('provider',choices=['claude','codex']);a=p.parse_args()
rec=STATE/'role-probes'/a.provider/'explore'
if not (rec/'summary.json').exists():
    workspace=rec/'workspace'
    if workspace.exists():
        raise RuntimeError('Incomplete role probe exists; inspect before retry')
    create(workspace,'cache_fix',1)
    result=run_cli(a.provider,'mixed',workspace,rec,
        'Read TASK.md and ttl_cache.py. Do not modify files. In under 100 words, identify three contract violations and cite the relevant code. This is a read-only exploration probe.',
        role='explore',timeout=90)
    dump(rec/'summary.json',result)
    print(json.dumps({'probe':a.provider,'model':result['model_requested'],'error':result['is_error'],'result':result['result']}),flush=True)
subprocess.run(['python3',str(PROJECT/'run_benchmark.py'),a.provider,'--tasks','cache_fix','scheduler','--seeds','1','2','--arms','delegated'],check=True)
