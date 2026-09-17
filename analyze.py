"""Aggregate all main and worker calls; distinguish tokens from reference pricing."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import statistics

from lab import STATE, dump

# USD per million tokens, standard API rates checked on 2026-09-14.
# These are a comparison index, NOT actual subscription charges or quota weights.
RATES = {
    'gpt-6-astra': (10.0, 1.0, 12.5, 50.0),
    'gpt-5.6-terra': (2.0, 0.2, 2.5, 12.0),
    'gpt-5.6-luna': (0.2, 0.02, 0.25, 1.2),
}
SOURCES = {model:'https://developers.openai.com/api/docs/models/'+model for model in RATES}


def call_metrics(call):
    u=call.get('usage',{})
    if call['provider']=='codex':
        inp=u.get('input_tokens',0);cached=u.get('cached_input_tokens',0)
        writes=u.get('cache_write_input_tokens',0);out=u.get('output_tokens',0)
        fresh=max(0,inp-cached-writes)
        rates=RATES.get(call['model_requested'])
        ref=(fresh*rates[0]+cached*rates[1]+writes*rates[2]+out*rates[3])/1e6 if rates else None
    else:
        # modelUsage also includes any internal CLI helper calls. Do not add the
        # top-level usage again because that would double count the main model.
        entries=list(call.get('model_usage',{}).values())
        if entries:
            fresh=sum(x.get('inputTokens',0) for x in entries)
            cached=sum(x.get('cacheReadInputTokens',0) for x in entries)
            writes=sum(x.get('cacheCreationInputTokens',0) for x in entries)
            out=sum(x.get('outputTokens',0) for x in entries)
        else:
            fresh=u.get('input_tokens',0);cached=u.get('cache_read_input_tokens',0)
            writes=u.get('cache_creation_input_tokens',0);out=u.get('output_tokens',0)
        inp=fresh+cached+writes
        ref=call.get('reference_cost_usd')
    return {'input':inp,'cached_input':cached,'cache_write_input':writes,
            'fresh_input':fresh,'output':out,'total_cloud_tokens':inp+out,
            'reference_usd':ref or 0.0,'usage_complete':bool(u)}


def frontier_tokens(call):
    if call['role'] != 'main':
        return 0
    if call['provider'] == 'claude' and call.get('model_usage'):
        entries=[v for k,v in call['model_usage'].items()
                 if k == call['model_requested'] or v.get('canonicalModel') == call['model_requested']]
        return sum(sum(x.get(k,0) for k in ['inputTokens','cacheReadInputTokens','cacheCreationInputTokens','outputTokens']) for x in entries)
    return call_metrics(call)['total_cloud_tokens']


def collect():
    rows=[]
    for p in sorted((STATE/'runs').glob('*/summary.json')):
        s=json.loads(p.read_text())
        quality_path=p.parent/'quality-audit.json'
        if quality_path.exists():s['quality']=json.loads(quality_path.read_text())
        calls=s['calls'];main=s['main']
        metrics=[call_metrics(c) for c in calls]
        sums={key:sum(m[key] for m in metrics) for key in ['input','cached_input','cache_write_input','fresh_input','output','total_cloud_tokens','reference_usd']}
        local=s['local_calls']
        # Audit attempted/failed tool calls too, not only successful bridge output.
        attempted=defaultdict(int);failed=defaultdict(int);native=[]
        for raw in (p.parent/'calls').glob('*/stdout.jsonl'):
            tool_names={}
            for line in raw.read_text().splitlines():
                try:e=json.loads(line)
                except json.JSONDecodeError:continue
                item=e.get('item',{})
                if e.get('type')=='item.completed' and item.get('type')=='mcp_tool_call':
                    attempted[item.get('tool')]+=1
                    if item.get('status')=='failed' or item.get('error'):failed[item.get('tool')]+=1
                if e.get('type')=='item.completed' and item.get('type') in ['command_execution','file_change','collab_tool_call']:
                    native.append(item.get('type'))
                content=e.get('message',{}).get('content',[])
                for block in content if isinstance(content,list) else []:
                    if block.get('type')=='tool_use':
                        name=block.get('name','');tool_names[block.get('id')]=name
                        if name.startswith('mcp__lab__'):attempted[name.removeprefix('mcp__lab__')]+=1
                        else:native.append(name)
                    if block.get('type')=='tool_result' and block.get('is_error'):
                        failed[tool_names.get(block.get('tool_use_id'),'unknown')]+=1
        rows.append(dict(provider=s['provider'],arm=s['arm'],task=s['task'],seed=s['seed'],
            score=s['quality']['score'],fully_correct=s['quality']['fully_correct'],
            passed_checks=s['quality'].get('passed',0),total_checks=s['quality'].get('total',0),
            additional_contract_checks=s['quality'].get('posthoc_additional_checks',0),
            wall_seconds=main['wall_seconds'],cloud_calls=len(calls),worker_calls=len(calls)-1,
            frontier_tokens=sum(frontier_tokens(c) for c in calls),
            local_calls=len(local),local_tokens=sum(x.get('usage',{}).get('total_tokens',0) for x in local),
            local_seconds=sum(x.get('wall_seconds',0) for x in local),
            error=main['is_error'] or main['timed_out'],immutable_inputs_preserved=s['immutable_inputs_preserved'],
            worker_errors=sum(c['is_error'] or c['timed_out'] for c in calls if c['role']!='main'),
            all_usage_complete=all(m['usage_complete'] for m in metrics),
            attempted_tools=dict(attempted),failed_tools=dict(failed),native_tool_violations=native,
            models=[c['model_requested'] for c in calls],**sums))
    return rows


def aggregate(rows):
    groups=defaultdict(list)
    for r in rows:groups[(r['provider'],r['arm'])].append(r)
    out=[]
    for (provider,arm),rs in groups.items():
        entry={'provider':provider,'arm':arm,'runs':len(rs),
               'quality_mean':statistics.mean(r['score'] for r in rs),
               'fully_correct_runs':sum(r['fully_correct'] for r in rs),
               'errors':sum(r['error'] for r in rs)}
        for field in ['total_cloud_tokens','frontier_tokens','fresh_input','cached_input','cache_write_input',
                      'output','reference_usd','wall_seconds','local_tokens','local_seconds','worker_calls','local_calls',
                      'passed_checks','total_checks']:
            entry[field]=sum(r[field] for r in rs)
        out.append(entry)
    return out


def paired(rows):
    index={(r['provider'],r['task'],r['seed'],r['arm']):r for r in rows}
    pairs=[]
    for r in rows:
        if r['arm']!='frontier':continue
        for arm in ['mixed','delegated']:
            m=index.get((r['provider'],r['task'],r['seed'],arm))
            if not m:continue
            p={'provider':r['provider'],'task':r['task'],'seed':r['seed'],'arm':arm,
               'quality_delta':m['score']-r['score']}
            for field in ['total_cloud_tokens','frontier_tokens','fresh_input','reference_usd','wall_seconds']:
                p[field+'_saving_pct']=100*(1-m[field]/r[field]) if r[field] else None
            pairs.append(p)
    return pairs


def export(directory):
    directory.mkdir(parents=True,exist_ok=False)
    rows=collect()
    data={'rows':rows,'aggregate':aggregate(rows),'pairs':paired(rows),'rate_sources':SOURCES,
          'api_reference_rates_per_million':RATES,
          'subscription_quota_saving_pct':None,
          'subscription_quota_note':'CLI token usage and API reference cost cannot identify exact subscription quota deductions.'}
    dump(directory/'results.json',data)
    fields=[k for k,v in rows[0].items() if not isinstance(v,(list,dict))] if rows else []
    with (directory/'runs.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
    return data


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=export(a.output);print(json.dumps(data['aggregate'],ensure_ascii=False,indent=2))
