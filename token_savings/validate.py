"""Post-run integrity checks. Accuracy failures remain results, not discarded runs."""
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

from analyze import collect
from compact import compact_json, MAX_CHARS
from run import STATE, dump


def main():
    d=collect()
    if not d['complete']:raise RuntimeError('Incomplete measurement set')
    frozen=json.loads((STATE/'source-hashes.json').read_text())
    source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in frozen.items())
    before=json.loads((STATE/'before.json').read_text())
    global_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v['sha256'] for p,v in before['files'].items())
    service_before=json.loads((STATE/'system-services-before.json').read_text())
    services={n:subprocess.run(['systemctl','show',n,'-p','MainPID','-p','ActiveState','-p','ActiveEnterTimestampMonotonic'],capture_output=True,text=True).stdout.strip() for n in service_before}
    with urllib.request.urlopen('http://127.0.0.1:11434/props',timeout=4) as r:props=json.load(r)
    capsules=[];discipline=[]
    for p in sorted((STATE/'runs').glob('*/summary.json')):
        s=json.loads(p.read_text());rec=p.parent
        records=[json.loads(t.read_text()) for t in sorted((rec/'tools').glob('*.json'))]
        calls=[x['tool'] for x in records]
        discipline.append(calls.count('local_brief')==(1 if s['arm']=='tool' else 0))
        if s['arm']=='tool':discipline.append(calls[0]=='local_brief')
        c=rec/'capsule.json'
        if c.exists():
            obj=json.loads(c.read_text());root=Path(json.loads((rec/'task.json').read_text())['root'])
            matches=[]
            for e in obj['evidence']:
                lines=(root/e['path']).read_text().splitlines()
                actual='\n'.join(f'{i}: {lines[i-1]}' for i in range(e['start_line'],e['end_line']+1))
                matches.append(actual==e['text'])
            capsules.append({'run':rec.name,'characters':len(compact_json(obj)),
                'within_budget':len(compact_json(obj))<=MAX_CHARS,'source_matches':all(matches)})
    report=dict(complete=True,runs=d['run_count'],frozen_sources_unchanged=source_unchanged,
        global_settings_and_adapters_unchanged=global_unchanged,services_unchanged=services==service_before,
        services=services,local_model_unchanged=props.get('model_path')==before['local']['model_path'],
        cli_errors=sum(r['error'] for r in d['rows']),usage_complete=all(r['complete'] for r in d['rows']),
        inputs_preserved=all(r['inputs_preserved'] for r in d['rows']),routing_discipline=all(discipline),
        capsules=capsules,quality={'passed':sum(r['passed'] for r in d['rows']),'checks':sum(r['checks'] for r in d['rows'])})
    dump(STATE/'validation.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['capsules','services']},indent=2))
    if not all([source_unchanged,all(x['within_budget'] and x['source_matches'] for x in capsules),
                report['usage_complete'],report['inputs_preserved'],report['routing_discipline']]):
        raise RuntimeError('Integrity issue: inspect validation.json before reporting')

if __name__=='__main__':main()
