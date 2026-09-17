"""Audit measured runs and export paired totals without estimating quota or prices."""
import csv
import json
from pathlib import Path
import statistics

from run import STATE, TASKS, dump


def citation_audit(root, submission):
    results = []
    for citation in submission.get('evidence', []):
        valid = False
        try:
            name = citation['path']; p = (root / name).resolve()
            start, end = citation['start_line'], citation['end_line']
            lines = p.read_text().splitlines() if p.is_relative_to(root.resolve()) and not Path(name).is_absolute() else []
            text = ' '.join('\n'.join(lines[start-1:end]).split())
            quote = ' '.join(citation['quote'].split())
            valid = type(start) is int and type(end) is int and 1 <= start <= end <= len(lines) and end-start < 10 and len(quote) >= 5 and quote in text
        except (KeyError, TypeError, OSError):
            pass
        results.append(dict(citation=citation, exact_source_match=valid))
    return dict(total=len(results), authentic=sum(x['exact_source_match'] for x in results), details=results)


def analyze():
    rows = []; details = []
    for repetition in (1,2):
      for task in TASKS:
        for provider in ('claude', 'codex'):
            for arm in ('frontier', 'mixed'):
                suffix = '' if repetition == 1 else f'-r{repetition}'
                rec = STATE / 'runs' / f'{task}-{provider}-{arm}{suffix}'
                if not (rec / 'summary.json').exists(): continue
                s = json.loads((rec / 'summary.json').read_text())
                td = json.loads((rec / 'task.json').read_text())
                submission = json.loads((rec / 'submission.json').read_text()) if (rec / 'submission.json').exists() else {}
                citations = citation_audit(Path(td['root']), submission)
                local = s['local'] or {}; lu = local.get('usage_this_call', {})
                row = dict(task=task, provider=provider, arm=arm, repetition=repetition, seconds=s['main']['wall_seconds'],
                           passed=s['quality']['passed'], checks=s['quality']['total'],
                           accuracy=s['quality']['score'], fully_correct=s['quality']['fully_correct'],
                           **s['usage'], tools=sum(s['tool_counts'].values()), tool_errors=s['tool_errors'],
                           local_seconds=local.get('wall_seconds', 0),
                           local_input_tokens=lu.get('prompt_tokens', 0), local_output_tokens=lu.get('completion_tokens', 0),
                           local_cached_tokens=lu.get('cached_tokens', lu.get('prompt_tokens_details', {}).get('cached_tokens', 0)),
                           local_partial=local.get('partial', False), local_truncated=local.get('truncated', False),
                           citations=citations['total'], authentic_citations=citations['authentic'],
                           evidence_recall=s['quality'].get('evidence_recall'), evidence_precision=s['quality'].get('evidence_precision'),
                           main_error=s['main']['is_error'], immutable=s['inputs_preserved'],
                           delegation_valid=(s['tool_counts'].get('delegate_task', 0)==1 and s['delegated_before_reads']) if arm=='mixed' else s['tool_counts'].get('delegate_task', 0)==0)
                rows.append(row); details.append(dict(run=rec.name, citations=citations, main=s['main'], quality=s['quality']))
    aggregates=[]; pairs=[]
    for provider in ('claude','codex'):
        for arm in ('frontier','mixed'):
            group=[r for r in rows if r['provider']==provider and r['arm']==arm]
            if not group: continue
            totals={k:sum(r[k] for r in group) for k in ('seconds','passed','checks','input_tokens','cached_input_tokens','output_tokens','total_tokens','noncached_plus_output','local_seconds','local_input_tokens','local_output_tokens','local_cached_tokens','citations','authentic_citations')}
            aggregates.append(dict(provider=provider,arm=arm,n=len(group),median_seconds=statistics.median(r['seconds'] for r in group),mean_seconds=totals['seconds']/len(group),fact_accuracy=totals['passed']/totals['checks'],fully_correct=sum(r['fully_correct'] for r in group),**totals))
        for repetition in (1,2):
          for task in TASKS:
            matched={r['arm']:r for r in rows if r['provider']==provider and r['task']==task and r['repetition']==repetition}
            if set(matched)!={'frontier','mixed'}:continue
            direct, delegated=matched['frontier'],matched['mixed']
            pairs.append(dict(provider=provider,task=task,repetition=repetition,
                              token_saving_pct=100*(1-delegated['total_tokens']/direct['total_tokens']),
                              noncached_saving_pct=100*(1-delegated['noncached_plus_output']/direct['noncached_plus_output']),
                              time_change_pct=100*(delegated['seconds']/direct['seconds']-1),
                              accuracy_change=delegated['accuracy']-direct['accuracy']))
    result=dict(rows=rows,aggregates=aggregates,pairs=pairs,complete=len(rows)==32,
                protocol_valid=all(r['immutable'] and r['delegation_valid'] and r['complete'] and not r['main_error'] for r in rows))
    output=STATE/'analysis';output.mkdir(exist_ok=True)
    dump(output/'results.json',result);dump(output/'audit.json',details)
    if rows:
        with (output/'measurements.csv').open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:result[k] for k in ('complete','protocol_valid','aggregates','pairs')},ensure_ascii=False,indent=2))
    return result


if __name__=='__main__': analyze()
