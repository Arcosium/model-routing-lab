"""Post-run content review; preserve frozen exact-match scores alongside this audit."""
import json

from run import STATE, dump
from analyze import citation_audit
from pathlib import Path


def review():
    data=json.loads((STATE/'analysis/results.json').read_text())
    rows=[]
    for row in data['rows']:
        name=f"{row['task']}-{row['provider']}-{row['arm']}"+('' if row['repetition']==1 else f"-r{row['repetition']}")
        rec=STATE/'runs'/name
        summary=json.loads((rec/'summary.json').read_text())
        submission=json.loads((rec/'submission.json').read_text())
        quality=summary['quality']
        failed=[x for x in quality.get('facts',quality.get('checks',[])) if not x['passed']]
        accepted=[];remaining=[]
        for item in failed:
            # This exact response was checked against parsing/headers.py and the question.
            # The question requests header_unit but does not require a bare enum value.
            if (row['task']=='call_chain' and item.get('field')=='header_unit'
                and item.get('actual')=='seconds (Retry-After: "120" = 120 whole seconds)'
                and item.get('expected')=='seconds'):
                accepted.append(dict(item,reason='Correct unit and value; explanatory parenthesis, not a factual error. Exact-match score retained.'))
            else:remaining.append(item)
        result=dict(run=name,provider=row['provider'],arm=row['arm'],task=row['task'],
                    repetition=row['repetition'],strict_passed=row['passed'],total=row['checks'],
                    content_passed=row['passed']+len(accepted),format_only_differences=accepted,
                    remaining_failures=remaining)
        if row['task'] in ('call_chain','change_impact'):
            gold=json.loads((STATE/'tasks'/row['task']/'grading/gold.json').read_text())
            taskdata=json.loads((rec/'task.json').read_text())
            source_check=citation_audit(Path(taskdata['root']),submission)
            valid_citations=[c['citation'] for c in source_check['details'] if c['exact_source_match']]
            anchors=[(claim,a) for claim,values in gold['anchors'].items() for a in values]
            # Presence of required source spans across the entire answer, independent of
            # which answer field a correct source excerpt was attached to.
            covered=[]
            for claim,a in anchors:
                present=any(c['path']==a['path'] and c['start_line']<=a['line']<=c['end_line'] for c in valid_citations)
                covered.append(dict(claim=claim,path=a['path'],line=a['line'],present=present))
            result['required_source_spans']=len(covered)
            result['included_source_spans']=sum(x['present'] for x in covered)
            result['source_span_details']=covered
        rows.append(result)
    value=dict(method='Manual review of exact-match failures plus source-span presence across the full answer. Original graders and scores unchanged.',
               limitations='Source-span presence is not a claim-by-claim proof; original anchor precision treats extra valid evidence as non-matching.',
               rows=rows)
    dump(STATE/'analysis/content-review.json',value)
    print(json.dumps({'runs':len(rows),'format_only':sum(len(r['format_only_differences']) for r in rows),
                      'remaining_failures':[r for r in rows if r['remaining_failures']],
                      'content_correct':sum(r['content_passed']==r['total'] for r in rows)},ensure_ascii=False,indent=2))
    return value


if __name__=='__main__':review()
