"""Accounting and hidden evidence review; never imported by workers."""
import csv
import json
from pathlib import Path
import statistics
from run import STATE, dump


def source_audit(record, summary):
    task=json.loads((record/'task.json').read_text());root=Path(task['root'])
    submission=json.loads((record/'submission.json').read_text()) if (record/'submission.json').exists() else {}
    visible=set();cited=set();valid=0
    def span(path,a,b,target):
        for i in range(a,b+1):target.add((path,i))
    if summary['arm']=='preflight' and (record/'capsule.json').exists():
        for e in json.loads((record/'capsule.json').read_text())['evidence']:
            span(e['path'],e['start_line'],e['end_line'],visible)
    for p in sorted((record/'tools').glob('*.json')):
        t=json.loads(p.read_text());r=t['result']
        if t['is_error']:continue
        if t['tool']=='local_brief':
            for e in r.get('evidence',[]):span(e['path'],e['start_line'],e['end_line'],visible)
        elif t['tool']=='read_evidence':
            for e in r:span(e['path'],e['start_line'],e['end_line'],visible)
        elif t['tool']=='read_files':
            for f in r['files']:
                for line in f['content'].splitlines():
                    n=line.partition(':')[0]
                    if n.isdigit():visible.add((f['path'],int(n)))
        elif t['tool']=='search':
            for e in r['matches']:visible.add((e['path'],e['line']))
    unseen=[]
    for e in submission.get('evidence',[]):
        lines=(root/e['path']).read_text().splitlines();a,b=e['start_line'],e['end_line']
        valid+=e['quote']=='\n'.join(lines[a-1:b])
        span(e['path'],a,b,cited)
        for i in range(a,b+1):
            if lines[i-1].strip() and (e['path'],i) not in visible:unseen.append([e['path'],i])
    if task['kind']=='repository':
        gold=json.loads((STATE/'tasks'/f"{task['task']}-s{task['seed']}"/'grading/gold.json').read_text())
        required={(a['path'],a['line']) for aa in gold['anchors'].values() for a in aa}
    elif task['task']=='incident':
        required=set()
        for i,line in enumerate((root/'service.log').read_text().splitlines(),1):
            if any('event='+ev+' ' in line for ev in ['E017','E023','E024','E051','E088','E089']):
                required.add(('service.log',i))
    else:
        required={('final-notice.txt',i) for i in range(1,10)}|{('amendment-2.txt',i) for i in range(2,5)}
    return {'citations':len(submission.get('evidence',[])),'exact_quotes':valid,
        'required_spans':len(required),'required_seen':len(required&visible),'required_cited':len(required&cited),
        'missing_seen':sorted(required-visible),'missing_cited':sorted(required-cited),'unseen_citations':unseen}


def collect():
    rows=[]
    for p in sorted((STATE/'runs').glob('*/summary.json')):
        s=json.loads(p.read_text());r={k:s[k] for k in ['provider','task','seed','arm']}
        r.update(s['usage']);r.update(seconds=s['end_to_end_seconds'],cloud_seconds=s['main']['wall_seconds'],
            passed=s['quality']['passed'],checks=s['quality']['total'],
            tools=sum(s['tool_counts'].values()),tool_errors=s['tool_errors'],
            error=s['main']['is_error'],inputs_preserved=s['inputs_preserved'],
            reply_chars=s['tool_reply_characters'],local_seconds=(s['local'] or {}).get('wall_seconds',0),
            capsule_chars=(s['local'] or {}).get('capsule_characters',0),
            gaps=(s['local'] or {}).get('gaps',[]))
        r['evidence']=source_audit(p.parent,s)
        load=p.parent/'local-load-before.json'
        r['load']=json.loads(load.read_text()) if load.exists() else {}
        rows.append(r)
    groups=[]
    for provider in ['claude','codex']:
        for arm in ['direct','tool','preflight']:
            subset=[r for r in rows if r['provider']==provider and r['arm']==arm]
            if not subset:continue
            g=dict(provider=provider,arm=arm,runs=len(subset))
            for k in ['input_tokens','cached_input_tokens','output_tokens','total_tokens','noncached_plus_output','passed','checks','tools','tool_errors']:
                g[k]=sum(r[k] for r in subset)
            for k in ['seconds','cloud_seconds','local_seconds','capsule_chars']:
                g['mean_'+k]=statistics.mean(r[k] for r in subset)
            g['median_seconds']=statistics.median(r['seconds'] for r in subset)
            g['errors']=sum(r['error'] for r in subset);g['gaps']=sum(bool(r['gaps']) for r in subset)
            g['evidence']={k:sum(r['evidence'][k] for r in subset) for k in ['citations','exact_quotes','required_spans','required_seen','required_cited']}
            groups.append(g)
    comparisons=[]
    for g in groups:
        if g['arm']=='direct':continue
        base=next(x for x in groups if x['provider']==g['provider'] and x['arm']=='direct')
        comparisons.append(dict(provider=g['provider'],arm=g['arm'],**{
            k+'_change_pct':100*(g[k]/base[k]-1) for k in ['total_tokens','noncached_plus_output','mean_seconds']}))
    return dict(complete=len(rows)==48,run_count=len(rows),groups=groups,comparisons=comparisons,rows=rows)


if __name__=='__main__':
    result=collect();out=STATE/'analysis';out.mkdir(exist_ok=True)
    dump(out/'results.json',result)
    if result['rows']:
        keys=[k for k in result['rows'][0] if k not in ['gaps','evidence','load']]
        with (out/'measurements.csv').open('w') as f:
            w=csv.DictWriter(f,keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in result['rows'])
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))
