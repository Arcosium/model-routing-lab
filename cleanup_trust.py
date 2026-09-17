"""Remove only project-trust entries created for this experiment by Codex CLI."""
import copy
import hashlib
import json
from pathlib import Path
import re
import tomllib
from lab import STATE,backup,dump

path=Path('/home/arcosium/.codex/config.toml')
before=path.read_bytes();stamp=path.stat().st_mtime_ns
current=tomllib.loads(before.decode())
original=tomllib.loads((STATE/'backups/.codex-config.toml').read_text())
expected=copy.deepcopy(current)
targets={k for k in current.get('projects',{}) if k.startswith(str(STATE)+'/') and k not in original.get('projects',{})}
for key in targets:expected['projects'].pop(key)
parts=re.split(r'(?m)(?=^\[)',before.decode());kept=[];removed=set()
for part in parts:
    try:entry=tomllib.loads(part)
    except tomllib.TOMLDecodeError:entry={}
    projects=entry.get('projects',{})
    if set(entry)=={'projects'} and len(projects)==1 and set(projects)<=targets:
        removed.update(projects)
    else:kept.append(part)
after=''.join(kept).encode()
if removed!=targets or tomllib.loads(after.decode())!=expected:
    raise RuntimeError('Cannot isolate experiment trust entries without other changes')
if after!=before:
    backup(path,STATE/'backups')
    if path.stat().st_mtime_ns!=stamp or path.read_bytes()!=before:
        raise RuntimeError('Config changed during cleanup; preserving the newer version')
    path.write_bytes(after)
result={'removed_experiment_trust_entries':len(removed),'other_current_settings_preserved':True,
        'semantically_equal_to_original':expected==original,
        'byte_equal_to_original':after==(STATE/'backups/.codex-config.toml').read_bytes()}
dump(STATE/'trust-cleanup.json',result)
print(json.dumps(result))
