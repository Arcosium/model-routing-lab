"""Paired benchmark runner; alternating arm order reduces time/cache order bias."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from benchmarks import TASKS, create
from lab import PROJECT, STATE, dump, run_cli


def one(provider, arm, task, seed):
    rec=STATE/'runs'/f'{provider}-{task}-s{seed}-{arm}'
    if (rec/'summary.json').exists():
        return json.loads((rec/'summary.json').read_text())
    workspace=rec/'workspace'
    if workspace.exists():
        raise RuntimeError(f'Incomplete run exists: {rec}; preserve and inspect it before retry')
    create(workspace,task,seed)
    before={str(p.relative_to(workspace)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in workspace.rglob('*') if p.is_file()}
    print(json.dumps({'event':'start','provider':provider,'arm':arm,'task':task,'seed':seed}),flush=True)
    result=run_cli(provider,arm,workspace,rec,'Read TASK.md and complete the task. Write the required artifacts.',timeout=420)
    # Run candidate grading outside the agent workspace and cap execution time.
    try:
        p=subprocess.run(['python3',str(PROJECT/'benchmarks.py'),'grade',str(workspace),task,'--seed',str(seed)],
                         capture_output=True,text=True,timeout=20)
        quality=json.loads(p.stdout)
    except Exception as e:
        quality={'score':0,'fully_correct':False,'error':type(e).__name__}
    immutable={k:v for k,v in before.items() if k=='TASK.md' or k.startswith('tests/') or k.endswith('.txt') or k.endswith('.log')}
    valid=all((workspace/k).exists() and hashlib.sha256((workspace/k).read_bytes()).hexdigest()==v for k,v in immutable.items())
    calls=[json.loads(p.read_text()) for p in (rec/'calls').glob('*/result.json')]
    tools=[json.loads(p.read_text()) for p in (rec/'tools').glob('*.json')]
    counts={}
    for t in tools:counts[t['tool']]=counts.get(t['tool'],0)+1
    summary={'provider':provider,'arm':arm,'task':task,'seed':seed,'main':result,
             'quality':quality,'immutable_inputs_preserved':valid,'calls':calls,'tool_counts':counts,
             'local_calls':[json.loads(t['result']) for t in tools if t['tool']=='local_analyze']}
    dump(rec/'summary.json',summary)
    print(json.dumps({'event':'done','provider':provider,'arm':arm,'task':task,'seed':seed,
                      'score':quality['score'],'seconds':result['wall_seconds'],'error':result['is_error'],
                      'tools':counts,'calls':len(calls)}),flush=True)
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('provider',choices=['claude','codex'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1,2]);p.add_argument('--tasks',nargs='+',choices=TASKS,default=list(TASKS))
    p.add_argument('--arms',nargs='+',choices=['frontier','mixed','delegated'])
    a=p.parse_args()
    for seed in a.seeds:
        for index,task in enumerate(a.tasks):
            arms=a.arms or (['frontier','mixed'] if (index+seed)%2 else ['mixed','frontier'])
            for arm in arms:
                one(a.provider,arm,task,seed)
