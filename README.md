# Model routing lab

Experimental profiles and a controlled benchmark for subscription-based Claude Code,
Codex CLI, and the existing local `arc-local` Qwen endpoint. Global Claude/Codex
settings are not changed. This is not enabled for production projects.

`state` is a gitignored symlink to the private experiment directory under vault.
Credentials, session output, model replies, workspaces, backups, and results stay
there. Source files and synthetic task generators contain no user data.

The main models are Opus 5 and GPT-6 Astra, both at medium effort. Fable was
replaced with Opus 5 at the user's explicit request after its quota was exhausted. The mixed
profiles expose a local analysis tool and bounded subscription CLI workers:
Sonnet/Haiku for Claude, Terra/Luna for Codex. Worker calls use fresh CLI contexts.
The shared MCP server scopes file access to the task workspace, protects task
requirements and public tests, backs up overwritten files, and records each call.
Native multi-agent tools are disabled during this controlled experiment so that
worker usage can be collected without double counting or missing child sessions.

## Commands

Run from this directory. The existing `state` setup must be present.

```bash
python3 -m unittest test_harness -v
python3 run_benchmark.py codex --seeds 1 2
python3 run_benchmark.py claude --seeds 1 2
python3 run_role_checks.py codex
python3 run_role_checks.py claude
python3 audit_quality.py
python3 cleanup_trust.py
python3 analyze.py --output state/artifacts/analysis-new
python3 report.py --output state/artifacts/report-new
```

Do not enable usage credits without the user's separate authorization.
Existing completed benchmark runs are reused; incomplete
runs are preserved and require inspection before retrying.

Four tasks cover incident analysis, revision-aware requirements extraction, a TTL
cache bug fix, and a scheduling feature. Each uses an independent deterministic
grader outside the agent workspace. The benchmark compares identical task data,
main model, effort, and base tools in both arms. Only routing access/instructions
differ. It alternates arm order and reports cache reads separately.

Results are a small synthetic benchmark, not a production quality guarantee.
Reported API-equivalent prices are a comparison index, not subscription charges.
Exact subscription quota savings are not observable from these token counters.

The final post-run audit adds one existing-contract edge case to every cache
artifact: deleting an expired but still stored entry must report its removal.
`quality-audit.json` preserves the original count and identifies the additional
check. The analyzer uses that audited result when present. Agent artifacts and
original summaries are not overwritten.

Codex CLI automatically adds trust entries for temporary workspaces despite
`--ignore-user-config`. After all Codex calls finish, `cleanup_trust.py` backs up
the current config and removes only this experiment's new entries, preserving
unrelated edits. Global model and routing settings are never configured by the lab.

The `delegated` arm is a separate exploratory comparison: each code task must
visit the implementation worker exactly once, followed by main-model review.
It was added after both main models handled the small code tasks directly in the
automatic `mixed` arm. Its matched baseline is the same task and seed in
`frontier`; do not pool it into the primary automatic-routing result.
`run_role_checks.py` also probes the read-only exploration model. Probe usage and
initial setup/failed preflight usage are excluded from paired task totals.

All runtime subprocess state, including browser review artifacts, must remain in
the existing private `state` target. The experiment uses only synthetic inputs;
its file-tool restrictions are not a sandbox for executing hostile Python code.
