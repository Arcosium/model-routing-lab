"""Experimental evidence capsule. No grading knowledge or cloud calls live here."""
import contextlib
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, '/home/arcosium/projects/claude-cooperation')
import local_qwen as api

ORIGINAL_STATE = api.STATE
MAX_CHARS = 6500
DOC_REQUEST = '''\nReturn ONLY a JSON object with keys answer and evidence.
answer must contain all requested answer keys with exact requested types.
evidence is a list of at most 12 objects {claim,path,start_line,end_line}.
Use absolute source paths and actual 1-based lines, at most 10 lines per object.
Select source lines sufficient to independently check every answer. Include the
cause, identifiers, units, corrective action and observed outcome if relevant.
Preserve event IDs separately from timestamps, actions separately from outcomes.
Consolidate adjacent evidence; no commentary, quotes, hashes or file inventories.
'''
REPO_REQUEST = '''\nIn submit_answer, put the requested answer object as compact JSON
in summary. Include authentic source spans sufficient to check the entire active
chain and all conclusions. Cite imports as well as calls, and preserve units.
Omit prose restatements and source inventories. Do not read any hidden grader.
'''


def compact_json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


def parse_object(text):
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == '{':
            try:
                value, _ = decoder.raw_decode(text[i:])
                if isinstance(value, dict):
                    return value
            except ValueError:
                pass
    raise ValueError('No JSON object in local response')


@contextlib.contextmanager
def shared_slot():
    start = time.monotonic()
    with (ORIGINAL_STATE / 'qwen.lock').open('a') as f:
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - start > api.CONFIG['queue_timeout_seconds']:
                    raise TimeoutError('Local worker busy')
                time.sleep(.1)
        yield


def make_capsule(root, raw, kind, max_chars=MAX_CHARS):
    """Resolve model-selected spans against unchanged files, never trust model quotes."""
    root = Path(root).resolve()
    warnings = []
    if kind == 'documents':
        parsed = parse_object(raw['analysis'])
        draft, spans = parsed.get('answer', {}), parsed.get('evidence', [])
    else:
        try:
            draft = parse_object(raw['analysis'])
        except ValueError:
            draft = raw.get('analysis', '')[:1800]
        spans = raw.get('evidence', [])
    capsule = {'draft': draft, 'evidence': [], 'gaps': warnings}
    sources = {str(Path(s['path']).resolve()): s['sha256'] for s in raw.get('sources', [])}
    if raw.get('truncated') or raw.get('partial'):
        warnings.append('Local response incomplete; check missing facts directly.')
    seen = set()
    for span in spans:
        try:
            name = Path(span['path'])
            path = (root / name).resolve(strict=True)
            if not path.is_relative_to(root) or path == root:
                raise ValueError('Span outside task root')
            path, source, digest = api.read_safe(str(path))
            if sources.get(str(path)) != digest:
                raise ValueError('Source changed or not observed by local worker')
            lines = source.splitlines()
            a, b = span['start_line'], span['end_line']
            if type(a) is not int or type(b) is not int or not 1 <= a <= b <= len(lines) or b-a >= 10:
                raise ValueError('Invalid line range')
            # One line of surrounding context helps preserve negations and imports.
            a, b = (1, len(lines)) if len(lines) <= 24 else (max(1, a-1), min(len(lines), b+1))
            key = (str(path), a, b)
            if key in seen:
                continue
            seen.add(key)
            item = {'path': str(path.relative_to(root)), 'start_line': a, 'end_line': b,
                    'text': '\n'.join(f'{i}: {lines[i-1]}' for i in range(a, b+1))}
            capsule['evidence'].append(item)
            if len(compact_json(capsule)) > max_chars - 180:
                capsule['evidence'].pop()
                warnings.append('Evidence budget reached; read omitted evidence directly.')
                break
        except (ValueError, KeyError, TypeError, OSError) as exc:
            warnings.append(type(exc).__name__ + ': invalid or changed source span')
    if not capsule['evidence']:
        warnings.append('No valid source spans. Solve using direct source tools.')
    if len(compact_json(capsule)) > max_chars:
        capsule['draft'] = 'Draft omitted: exceeds size budget. Use source evidence.'
    if len(compact_json(capsule)) > max_chars:
        return {'draft': {}, 'evidence': [], 'gaps': ['Capsule exceeds budget. Read sources directly.']}
    return capsule


def prepare(root, task, record):
    record = Path(record)
    if (record / 'capsule.json').exists():
        raise RuntimeError('Refusing to regenerate an existing capsule')
    record.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    api.STATE = record / 'local-state'
    api.STATE.mkdir(mode=0o700)
    api.CONFIG = dict(api.CONFIG, cache_seconds=0)
    api.local_slot = shared_slot
    raw = {}
    try:
        if task['kind'] == 'documents':
            raw = api.analyze_files(task['question'] + DOC_REQUEST,
                                    [str(Path(root)/p) for p in task['source_files']], 1600)
        else:
            raw = api.explore_repository(task['question'] + REPO_REQUEST, str(root), 10)
        capsule = make_capsule(root, raw, task['kind'])
    except Exception as exc:
        capsule = {'draft': {}, 'evidence': [], 'gaps': ['Local preparation failed: ' + type(exc).__name__ + '. Read sources directly.']}
    duration = time.monotonic() - start
    for name, obj in [('local-result.json',raw), ('capsule.json',capsule),
                      ('local-metrics.json', {'wall_seconds': duration,
                        'capsule_characters': len(compact_json(capsule)),
                        'usage': raw.get('usage_this_call',{}), 'gaps':capsule['gaps']})]:
        (record/name).write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    return capsule
