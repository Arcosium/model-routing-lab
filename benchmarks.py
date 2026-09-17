"""Synthetic paired tasks. Expected answers and hidden tests stay outside workspaces."""
from __future__ import annotations
import copy
import importlib.util
import json
from pathlib import Path
import random
import traceback

TASKS = ("incident", "requirements", "cache_fix", "scheduler")


def write(root, path, content):
    p = root / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def create(root: Path, name: str, seed: int):
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    if name == "incident":
        delay = 90 + 30 * seed
        events = []
        special = {
          24: f"event=E017 service=quota-worker deploy release=r{40+seed} retry_after_unit=milliseconds",
          61: f"event=E023 service=quota-worker request=req-{780+seed:04} response=429 Retry-After={delay} header_unit=seconds",
          62: f"event=E024 service=quota-worker request=req-{780+seed:04} parsed_delay_ms={delay} attempt=2",
          143: "event=E051 service=report-exporter error=DISK_FULL scope=export-only queue=reports",
          217: "event=E070 service=quota-worker metric=retry_backlog growth=rapid downstream=rate-limited",
          401: "event=E088 service=quota-worker config-change retry_after_unit=seconds release_rollback=false",
          405: f"event=E089 service=quota-worker next_retry_delay_ms={delay*1000} queue_growth=stopped",
          430: "event=E094 service=report-exporter error=DISK_FULL scope=export-only status=unresolved",
        }
        for i in range(480):
            msg = special.get(i, f"event=N{i:04} service={rng.choice(['catalog','search','metrics'])} status=200 duration_ms={rng.randrange(3,40)} health=ok batch={i//12}")
            events.append(f"2026-09-01T12:{i//60:02}:{i%60:02}Z {msg}")
        write(root, "service.log", "\n".join(events)+"\n")
        write(root, "TASK.md", """Investigate the retry storm using service.log. All data is synthetic.
Write answer.json with these exact keys:
affected_service, release, first_bad_request, header_seconds (integer),
applied_delay_ms (integer), correct_delay_ms (integer), mitigation (key=value),
distractor_service, rollback_required (boolean), evidence_events (list).
Identify the actual causal chain and distinguish the unrelated exporter outage.
Evidence must include the deployment, 429 response, parsed delay, and mitigation event IDs.
Do not invent observations. You may inspect selected portions instead of the whole file.
""")
    elif name == "requirements":
        old = ["ARCHIVED DRAFT. Superseded by amendment-2 and final-notice when they conflict.",
               "deadline=2026-10-01T18:00:00+09:00; team_limit=5; budget_krw=20000000",
               "formats=PDF,DOCX; signature=not-required; page_limit=20"]
        old += [f"Appendix item {i}: instrument calibration group {rng.randrange(10,99)}, reference batch {i+seed*100}; technical background only." for i in range(210)]
        write(root, "draft.txt", "\n".join(old))
        second = ["AMENDMENT 2. Overrides the archived draft. Later final notice overrides this document.",
                  "deadline=2026-10-05T17:00:00+09:00; team_limit=4; page_limit=12",
                  "formats=PDF; signature=required; budget_krw=18000000",
                  "Exclude cover and references from page count. Appendix pages count."]
        second += [f"Q&A {i}: keep instrument specification {i*3+seed}; no changes to eligibility, file formats, deadlines, or budget." for i in range(170)]
        write(root, "amendment-2.txt", "\n".join(second))
        final = ["FINAL NOTICE. Latest authoritative revision. Unmentioned amendment-2 terms remain in force.",
                 f"Submission deadline is 2026-10-{10+seed:02} at 16:30 Asia/Seoul. This is not the Q&A deadline.",
                 "The Q&A deadline remains 2026-10-03 at 12:00 Asia/Seoul.",
                 f"Budget ceiling is {15000000+seed*1000000} KRW inclusive of VAT.",
                 "Teams may contain no more than 3 members; solo submissions are permitted.",
                 "Submit exactly two files: proposal.pdf and budget.xlsx. Do not submit DOCX.",
                 "The proposal requires a signature. A scanned handwritten signature is accepted.",
                 "Keep amendment-2 page-count exclusions. There is no exception for appendix pages.",
                 "An unsigned proposal is rejected; it is not eligible for post-deadline correction."]
        write(root, "final-notice.txt", "\n".join(final))
        write(root,"TASK.md","""Extract the final requirements from these synthetic revision documents.
Priority: final-notice.txt > amendment-2.txt > draft.txt. Later documents only override stated fields.
Write answer.json using these exact keys:
deadline (ISO8601 with +09:00), qa_deadline (same), budget_krw (integer),
vat_included (boolean), max_team_members (integer), solo_allowed (boolean),
files (list of exact filenames), page_limit (integer),
excluded_from_page_count (list using cover/references/appendices),
appendices_count (boolean), signature_required (boolean),
scanned_signature_allowed (boolean), unsigned_correction_allowed (boolean).
Also include sources: an object mapping deadline, budget_krw, page_limit to source filenames.
""")
    elif name == "cache_fix":
        write(root,"ttl_cache.py",'''from copy import deepcopy

class TTLCache:
    def __init__(self, clock):
        self.clock = clock
        self.entries = {}

    def set(self, key, value, ttl):
        self.entries[key] = (self.clock() + ttl, value)

    def get(self, key, default=None):
        if not key or key not in self.entries:
            return default
        expires, value = self.entries[key]
        if self.clock() > expires:
            del self.entries[key]
            return default
        return value

    def delete(self, key):
        return bool(self.entries.pop(key, None))
''')
        write(root,"tests/test_public.py",'''import unittest
from ttl_cache import TTLCache
class Public(unittest.TestCase):
    def setUp(self):
        self.time = [100]
        self.c = TTLCache(lambda:self.time[0])
    def test_basic(self):
        self.c.set("a", 42, 10)
        self.assertEqual(self.c.get("a"),42)
    def test_expired(self):
        self.c.set("a", 42, 10)
        self.time[0]=111
        self.assertEqual(self.c.get("a","miss"),"miss")
    def test_delete(self):
        self.c.set("a", None, 10)
        self.assertTrue(self.c.delete("a"))
        self.assertFalse(self.c.delete("a"))
''')
        write(root,"TASK.md","""Fix ttl_cache.py while preserving the TTLCache API; use only the Python standard library.
Contract: any hashable key is valid, including 0, False, empty string, and None.
get returns the supplied default for a missing or expired entry. An entry expires
at now >= insertion_time + ttl. ttl <= 0 removes an existing entry immediately.
Stored values must be isolated from caller mutation: deep copy on set and on each
successful get. Do not copy the caller's default; return that exact object on a miss.
delete returns whether a stored entry was removed, including entries holding None.
Overwriting resets expiry. Separate cache instances must not share data.
Public tests cover only examples. Fix all contract issues and run public tests.
Do not change tests or TASK.md. Write the corrected implementation to ttl_cache.py.
""")
    elif name == "scheduler":
        write(root,"scheduler.py",'''def select_jobs(jobs, now, capacity):
    raise NotImplementedError
''')
        write(root,"tests/test_public.py",'''import unittest
from scheduler import select_jobs
class Public(unittest.TestCase):
    def test_priority(self):
        jobs=[dict(id="a",ready_at=0,priority=1,cost=1,group="a"),dict(id="b",ready_at=0,priority=2,cost=1,group="b")]
        self.assertEqual(select_jobs(jobs,1,1),["b"])
    def test_empty(self):
        self.assertEqual(select_jobs([],1,10),[])
    def test_future(self):
        self.assertEqual(select_jobs([dict(id="a",ready_at=5,priority=1,cost=1,group="a")],1,10),[])
''')
        write(root,"TASK.md","""Implement select_jobs(jobs, now, capacity) in scheduler.py using only the Python standard library.
Return a list of job IDs. Inputs are well-formed dicts with id (string), ready_at
(integer), priority (integer), cost (positive integer), group (string or None).
Select only jobs with ready_at <= now. Deduplicate IDs AFTER readiness filtering:
the first ready occurrence in input order wins, even if a later duplicate has
higher priority. Sort candidates by descending priority, then ascending ready_at,
then original input position. Greedily scan sorted candidates; skip jobs that do
not fit remaining capacity and continue scanning. At most one selected job per
nonempty group; group None or empty string does not create any conflict. A skipped
job must NOT reserve its group. capacity <= 0 returns []. Never mutate any input.
Public tests are examples; satisfy all contract details. Run public tests.
Do not change tests or TASK.md. Write the implementation to scheduler.py.
""")
    else:
        raise ValueError(name)


def grade(root: Path, name: str, seed: int):
    checks=[]
    def check(label, actual, expected):
        checks.append({"name":label,"passed":actual==expected,"actual":actual,"expected":expected})
    try:
        if name in ("incident","requirements"):
            a=json.loads((root/'answer.json').read_text())
            if name=="incident":
                expected=dict(affected_service='quota-worker',release=f'r{40+seed}',
                    first_bad_request=f'req-{780+seed:04}',header_seconds=90+30*seed,
                    applied_delay_ms=90+30*seed,correct_delay_ms=(90+30*seed)*1000,
                    mitigation='retry_after_unit=seconds',distractor_service='report-exporter',rollback_required=False)
                for k,v in expected.items():check(k,a.get(k),v)
                for event in ['E017','E023','E024','E088']:check('evidence:'+event,event in a.get('evidence_events',[]),True)
            else:
                expected=dict(deadline=f'2026-10-{10+seed:02}T16:30:00+09:00',
                  qa_deadline='2026-10-03T12:00:00+09:00',budget_krw=15000000+seed*1000000,
                  vat_included=True,max_team_members=3,solo_allowed=True,page_limit=12,
                  appendices_count=True,signature_required=True,scanned_signature_allowed=True,
                  unsigned_correction_allowed=False)
                for k,v in expected.items():check(k,a.get(k),v)
                check('files',sorted(a.get('files',[])),['budget.xlsx','proposal.pdf'])
                check('page exclusions',sorted(a.get('excluded_from_page_count',[])),['cover','references'])
                for k,v in dict(deadline='final-notice.txt',budget_krw='final-notice.txt',page_limit='amendment-2.txt').items():
                    check('source:'+k,a.get('sources',{}).get(k),v)
        elif name=='cache_fix':
            spec=importlib.util.spec_from_file_location('candidate_cache',root/'ttl_cache.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            clock=[100];c=mod.TTLCache(lambda:clock[0])
            for k in [0,'',None]:
                c.set(k,{'k':str(k)},10);check('falsy key '+str(k),c.get(k),{'k':str(k)})
            c.set('edge',1,10);clock[0]=110;check('expiry equality',c.get('edge'),None)
            for ttl in [0,-1]:
                c.set('gone',7,99);c.set('gone',8,ttl);check('nonpositive ttl '+str(ttl),c.get('gone'),None)
            x={'nested':[1]};c.set('copy',x,10);x['nested'].append(2)
            check('copy on set',c.get('copy'),{'nested':[1]})
            y=c.get('copy');y['nested'].append(3);check('copy on get',c.get('copy'),{'nested':[1]})
            default=[];check('default identity',c.get('missing',default) is default,True)
            c.set('none',None,9);check('stored none deletion',c.delete('none'),True);check('second delete',c.delete('none'),False)
            c.set('new',5,1);clock[0]=111;c.set('new',6,10);clock[0]=115;check('overwrite expiry',c.get('new'),6)
            c2=mod.TTLCache(lambda:clock[0]);check('instance separation',c2.get('new'),None)
            c.set(False,5,10);check('false key',c.get(False),5)
        elif name=='scheduler':
            spec=importlib.util.spec_from_file_location('candidate_scheduler',root/'scheduler.py')
            mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            def j(id,priority=1,ready_at=0,cost=1,group=None):return dict(id=id,priority=priority,ready_at=ready_at,cost=cost,group=group)
            cases=[
             ('empty',[],1,5,[]),('zero',[j('a')],1,0,[]),('negative',[j('a')],1,-1,[]),
             ('readiness boundary',[j('a',ready_at=1)],1,1,['a']),
             ('priority',[j('a'),j('b',priority=2)],1,1,['b']),
             ('earlier ready',[j('a',ready_at=1),j('b',ready_at=0)],1,1,['b']),
             ('stable ties',[j('z'),j('a')],1,2,['z','a']),
             ('first ready duplicate',[j('a',priority=1),j('a',priority=9),j('b',priority=2)],1,1,['b']),
             ('future duplicate ignored',[j('a',ready_at=3),j('a',ready_at=0)],1,2,['a']),
             ('skip overbudget',[j('a',priority=9,cost=8),j('b',cost=2)],1,3,['b']),
             ('same group',[j('a',group='g'),j('b',group='g')],1,9,['a']),
             ('none group',[j('a'),j('b')],1,2,['a','b']),
             ('empty group',[j('a',group=''),j('b',group='')],1,2,['a','b']),
             ('skipped does not reserve group',[j('a',priority=9,cost=8,group='g'),j('b',cost=1,group='g')],1,2,['b']),
             ('remaining capacity',[j('a',priority=9,cost=2),j('b',priority=8,cost=2),j('c')],1,3,['a','c']),
             ('negative priority',[j('a',priority=-2),j('b',priority=-1)],1,1,['b'])]
            for label,jobs,now,cap,expected in cases:
                before=copy.deepcopy(jobs)
                check(label,mod.select_jobs(jobs,now,cap),expected)
                check(label+' preserves input',jobs,before)
    except Exception as e:
        checks.append({'name':'artifact execution','passed':False,'error':type(e).__name__+': '+str(e)})
    expected_totals={'incident':13,'requirements':16,'cache_fix':14,'scheduler':32}
    passed=sum(x['passed'] for x in checks)
    return {'task':name,'seed':seed,'checks':checks,'passed':passed,
            'total':expected_totals[name],'score':passed/expected_totals[name],
            'fully_correct':passed==expected_totals[name]}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['create','grade'])
    p.add_argument('root',type=Path);p.add_argument('task',choices=TASKS);p.add_argument('--seed',type=int,default=1)
    a=p.parse_args()
    if a.action=='create':create(a.root,a.task,a.seed)
    else:print(json.dumps(grade(a.root,a.task,a.seed),ensure_ascii=False))
