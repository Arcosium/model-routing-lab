# Local delegation comparison

This experiment compares Claude Code (Opus 5) and Codex CLI (GPT-6 Astra), each
directly solving a task versus delegating exactly once to the installed
`claude-cooperation` local adapter and then verifying its answer. Both cloud
models use medium effort. No cloud implementation workers are involved.

The four tasks reuse the seed-1 incident, revision requirements, call-chain and
change-impact fixtures from the existing experiments. Inputs and graders are
frozen before execution. Each of the four client/routing cells is run twice;
the second repetition reverses the first repetition's order for that task.
The repeat was added after the initial local calls exposed server cache effects.

`local-qwen` is a tool name, not proof of the loaded weights. Record `/props` and
the model file name at execution time. The wrapper calls the existing production
`analyze_files` and `explore_repository` implementations without changing them.
It disables response-cache reuse, isolates logs and cache files under `state`,
and retains the installed server's shared inference lock. Server KV and provider
prompt caches remain enabled and their reported counts are retained.

## Reproduce

An ignored `state` symlink must point to a fresh private directory under vault.
Prepare isolated subscription CLI authentication there; never put credentials in
this source tree. Generated synthetic inputs live in the ignored `fixtures/`
directory under this project so the production adapter can enforce its project
root restriction. The grader and model output are outside those input roots.

```sh
python3 -m unittest test_compare -v
python3 run.py --setup
python3 run.py
python3 run.py --repeat 2
python3 analyze.py
```

Existing completed runs are reused; unfinished runs stop execution for inspection.
These commands do not install MCP servers, change global model preferences, enable
usage credits, restart services, or write to production projects.

Accuracy uses independent field checks. Repository evidence is additionally scored
against exact source anchors; citation authenticity is checked for all tasks.
Latency includes CLI startup, local inference, main-model verification and final
response. Cloud tokens include cached input, cache creation and output; cached
reads and local tokens are reported separately. There is no conversion from token
counts to subscription quota. Absolute token counts across vendors use different
tokenizers and hidden prompts. Harness setup and this supervising conversation are
outside task measurements. A small fixed sample cannot establish a universal policy.
