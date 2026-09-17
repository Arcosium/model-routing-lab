"""Post-run contract audit applied uniformly; preserve original grader results."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
from lab import PROJECT,STATE,dump

p=argparse.ArgumentParser();p.add_argument('--workspace',type=Path);a=p.parse_args()
if a.workspace:
    spec=importlib.util.spec_from_file_location('candidate_cache',a.workspace/'ttl_cache.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    now=[100];cache=m.TTLCache(lambda:now[0]);cache.set('expired',None,1);now[0]=101
    actual=cache.delete('expired')
    print(json.dumps({'name':'delete reports removal of an expired stored entry','passed':actual is True,'actual':actual,'expected':True}))
else:
    counts={}
    for rec in sorted((STATE/'runs').iterdir()):
        summary=rec/'summary.json'
        if not summary.exists():continue
        target=rec/'quality-audit.json'
        if target.exists():continue
        s=json.loads(summary.read_text());q=s['quality'];extra=[]
        if s['task']=='cache_fix':
            try:
                r=subprocess.run(['python3',str(PROJECT/'audit_quality.py'),'--workspace',str(rec/'workspace')],capture_output=True,text=True,timeout=10)
                extra=[json.loads(r.stdout)]
            except Exception as e:extra=[{'name':'expired stored entry deletion','passed':False,'error':str(e)}]
        passed=q['passed']+sum(x['passed'] for x in extra);total=q['total']+len(extra)
        result={**q,'checks':q['checks']+extra,'passed':passed,'total':total,'score':passed/total,
                'fully_correct':passed==total,'original_passed':q['passed'],'original_total':q['total'],
                'posthoc_additional_checks':len(extra),'reason':'Code review identified missing coverage for existing TASK.md delete contract; applied to all arms without changing artifacts.'}
        dump(target,result)
        counts[s['provider']]=counts.get(s['provider'],0)+len(extra)
    print(json.dumps({'new_checks_by_provider':counts}))
