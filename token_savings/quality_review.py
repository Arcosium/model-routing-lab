"""Supplemental type and field-citation audit, separate from the frozen fact grader."""
import json
from pathlib import Path
from run import STATE, dump


def review():
    rows=[]
    for p in sorted((STATE/'runs').glob('*/summary.json')):
        s=json.loads(p.read_text());rec=p.parent
        sub=json.loads((rec/'submission.json').read_text()) if (rec/'submission.json').exists() else {}
        answer=sub.get('answer',{});citations=sub.get('evidence',[])
        type_errors=[]
        checks=s['quality'].get('checks',s['quality'].get('facts',[]))
        for c in checks:
            field=c.get('field',c.get('name'))
            if field in answer and 'expected' in c and type(answer[field]) is not type(c['expected']):
                type_errors.append({'field':field,'actual_type':type(answer[field]).__name__,'expected_type':type(c['expected']).__name__})
        task=s['task']
        if task=='incident':
            anchors={'affected_service':[('service.log',25)],'release':[('service.log',25)],
                'first_bad_request':[('service.log',62)],'header_seconds':[('service.log',62)],
                'applied_delay_ms':[('service.log',63)],'correct_delay_ms':[('service.log',406)],
                'mitigation':[('service.log',402)],'distractor_service':[('service.log',144)],
                'rollback_required':[('service.log',402)]}
        elif task=='requirements':
            anchors={key:[('final-notice.txt',line)] for key,line in {
                'deadline':2,'qa_deadline':3,'budget_krw':4,'vat_included':4,
                'max_team_members':5,'solo_allowed':5,'files':6,
                'signature_required':7,'scanned_signature_allowed':7,'unsigned_correction_allowed':9}.items()}
            anchors.update(page_limit=[('amendment-2.txt',2)],
                excluded_from_page_count=[('amendment-2.txt',4)],appendices_count=[('amendment-2.txt',4)])
        else:
            g=json.loads((STATE/'tasks'/f"{task}-s{s['seed']}"/'grading/gold.json').read_text())
            anchors={key:[(e['path'],e['line']) for e in refs] for key,refs in g['anchors'].items()}
        missing=[]
        for field,refs in anchors.items():
            for path,line in refs:
                if not any(e['claim']==field and e['path']==path and e['start_line']<=line<=e['end_line'] for e in citations):
                    missing.append({'field':field,'path':path,'line':line})
        rows.append({'run':rec.name,'type_errors':type_errors,'missing_exact_field_anchors':missing})
    result={'note':'Supplemental review only. Missing exact anchor can still have valid alternative evidence; do not count automatically as a factual error.',
        'runs':len(rows),'type_errors':sum(len(r['type_errors']) for r in rows),
        'exact_field_anchor_gaps':sum(len(r['missing_exact_field_anchors']) for r in rows),'rows':rows}
    dump(STATE/'analysis/quality-review.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':review()
