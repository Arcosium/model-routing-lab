"""Grade explicit local JSON answers only; never infer a missing structured answer."""
import json
from pathlib import Path

from run import STATE, benchmarks, dump


def extract(text, required):
    decoder = json.JSONDecoder()
    for pos, character in enumerate(text):
        if character != '{': continue
        try: value, _ = decoder.raw_decode(text[pos:])
        except ValueError: continue
        if isinstance(value, dict) and all(key in value for key in required): return value
    return None


def audit():
    rows=[]
    for rec in sorted((STATE/'runs').iterdir()):
        if not (rec/'summary.json').exists() or not (rec/'local-result.json').exists(): continue
        summary=json.loads((rec/'summary.json').read_text())
        task=summary['task']
        if task not in ('incident','requirements'):continue
        local=json.loads((rec/'local-result.json').read_text())
        required=['affected_service','header_seconds'] if task=='incident' else ['deadline','page_limit']
        answer=extract(local.get('analysis',''),required)
        row=dict(run=rec.name,task=task,provider=summary['provider'],structured_answer_found=answer is not None)
        if answer is not None:
            directory=STATE/'local-quality'/rec.name
            dump(directory/'answer.json',answer)
            quality=benchmarks.grade(directory,task,1)
            row.update(passed=quality['passed'],total=quality['total'],score=quality['score'],
                       failed=[x for x in quality['checks'] if not x['passed']])
        rows.append(row)
    dump(STATE/'analysis/local-quality.json',rows)
    print(json.dumps(rows,ensure_ascii=False,indent=2))
    return rows


if __name__=='__main__':audit()
