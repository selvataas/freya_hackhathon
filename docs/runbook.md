# Runbook: final briefs (Sunday evening)

Step-by-step for the two final briefs. Read it end to end once before the briefs open.

Ground rules from the README and CLAUDE.md:

- The builder runs with one command, no manual step. The agent is never edited on the platform.
- Nothing from a final brief goes into the code or prompts: no rule, no value, no name. Fixing a crash is allowed.
- At most 30 minutes per brief, tests included. One build takes about 2 to 3 minutes.
- The agent runs on `freya.AGENT_LLM` (`experimental-5`); `freya.py` stays as the kit shipped it.
- We submit, per brief: the exported workflow, the code (this repo at a commit) and that run's trace.

## 0. Before the briefs open

```bash
cd freya_hackhathon
git pull                                   # the version we submit
source env.sh                              # FREYA_API_KEY, FREYA_API_URL, FREYA_BANK_TEAM_KEY, ANTHROPIC_API_KEY
python3 --version                          # 3.9 or newer; no packages needed
python3 -c "import sys; sys.path.insert(0,'builder'); import extract; print(extract.MODEL)"   # claude-opus-5-5
```

Check the budget (it must leave at least $3 for the two briefs; one brief costs about $0.50 to $0.80):

```bash
python3 - <<'EOF'
import json, glob
P = {"claude-opus-5-5": (4, 20), "claude-sonnet-5-5": (2, 10)}
t = 0
for f in glob.glob("traces/*.jsonl"):
    for l in open(f):
        e = json.loads(l)
        if e.get("event") == "model_call":
            i, o = P[e["model"]]; t += (e.get("input_tokens") or 0) * i / 1e6 + (e.get("output_tokens") or 0) * o / 1e6
print(f"spent so far ${t:.2f}")
EOF
```

Check the platform answers (a chat turn on the spike workflow, a few seconds):

```bash
python3 -c "import freya,json; w=json.load(open('.freya-agents.json'))['spike']['workflow_id']; print(freya.api('POST','/api/v2/chat/message',{'workflowId':w,'message':'Hello?','customerVariables':{'customer_id':'c_test','now':'2026-10-14T11:00'}}).get('response'))"
```

If it does not answer, the platform is down: wait and retry. Do not start a build on a dead platform (the build itself works, but the dry run and the save fail).

The workspace holds at most 10 workflows. Today: Base (brief-a), brief-b, spike. Each final brief adds one.

## 1. Put the briefs in place

One folder per final brief under `final/`. The tool API file goes next to the brief, never inside a brief folder
(a brief folder is read whole, every file as brief text).

```
final/
  <name1>/
    <name1>.md            # a clean brief: one file
    openapi.json          # that brief's tool API
  <name2>/
    <name2>/              # raw material: a folder of files (mail, policy, memo, code list), read in name order
      01-....txt
      ...
    openapi.json
```

- The slot (the workflow name) is the brief file name without extension, or the folder name. Pick names that do not
  clash with `brief-a`, `brief-b` or `spike`, otherwise the build overwrites that workflow.
- Raw material: name the files so that name order is reading order; a memo that changes the policy comes after it.
  Do not edit the content.
- If a final brief says it builds on another brief, pass both, in order (as `brief-a.md brief-b.md`).

## 2. Build

Use plain `python3`, Opus, no `--no-llm` (the first build must extract), and keep the log with `tee`:

```bash
mkdir -p traces submission
LLM_MODEL=claude-opus-5-5 python3 builder/build.py final/<name1>/<name1>.md final/<name1>/openapi.json 2>&1 | tee traces/final-<name1>.log
LLM_MODEL=claude-opus-5-5 python3 builder/build.py final/<name2>/<name2> final/<name2>/openapi.json 2>&1 | tee traces/final-<name2>.log
```

The last line is JSON: `{"slot", "workflow_id", "agent_id", "selftest", "warnings"}`. The trace is the newest
`traces/<time>-<slot>.jsonl`.

## 3. Checks after each build

1. The last line has a `workflow_id` and an `agent_id`. A traceback means a crash: see section 5.
2. `selftest` is `n/n`. A failed scenario is listed in the trace (`event: selftest`); read it before going on.
3. `warnings`: every warning is in the trace (`event: warning`). Most are harmless (an unknown value fell back to a safe
   default). Read each one.
4. The trace has: `start`, every `model_call` (model, purpose, tokens), `spec_compare`, `rendered` (nodes, tools),
   `selftest`, `dry_run` (valid), `saved` (workflow and agent id), `end` (build_seconds).
5. Read `out/<slot>.spec.json` against the brief. Reading is allowed, changing is not. Look at:
   call variable names, identity questions and wrong-answer limit, holidays, bands and deadlines, persuasion attempts,
   floor fields, outcome rows (`outcomes`), `custom_situations`, `unplaced_rules` (short or empty is normal),
   and for raw material: was every change of the memo applied.
6. No key in the trace or the log:

```bash
grep -E -c "fak_[A-Za-z0-9]{6,}|sk-ant-[A-Za-z0-9]{6,}|Bearer " traces/*<slot>*.jsonl traces/final-<slot>.log   # must be 0
```

7. Optional, if time is left: one chat turn against the new workflow to see the opening line (a chat skips the first code
   step, so only use it to see that the workflow starts).

## 4. Export, commit, submit

**Export right after every build**, before anything else touches the workflow. The submitted workflow must be the output
of the run whose trace we submit:

- If the builder runs again for a brief (a fix, a rebuild), the new run's trace, build log and export replace the old
  three together. Never mix a trace of one run with the export of another.
- The check below must pass for the three files that go into `submission/`.

```bash
# run the build, then export at once
LLM_MODEL=claude-opus-5-5 python3 builder/build.py final/<name>/<name>.md final/<name>/openapi.json 2>&1 | tee traces/final-<name>.log
python3 -c "import freya,json,sys; s=json.load(open('.freya-agents.json'))[sys.argv[1]]; print(freya.export_workflow(s['workflow_id'], 'submission/'+sys.argv[1]+'.workflow.json'))" <slot>
cp "$(ls -t traces/*-<slot>.jsonl | head -1)" submission/<slot>.trace.jsonl
cp traces/final-<name>.log submission/<slot>.build.log

# the export is this run's workflow: every field of the build output is in it, and the ids match the trace
python3 - <slot> <<'PY'
import json, sys
slot = sys.argv[1]
ex = json.load(open(f"submission/{slot}.workflow.json"))
built = json.load(open(f"out/{slot}.workflow.json"))
saved = [json.loads(l) for l in open(f"submission/{slot}.trace.jsonl") if '"event": "saved"' in l][-1]
def walk(a, b, p=""):
    # every field of ours must be in the export with the same value; the platform may add fields of its own
    if isinstance(a, dict):
        return sum((walk(v, b[k], p + "/" + k) if isinstance(b, dict) and k in b else [p + "/" + k] for k, v in a.items()), [])
    if isinstance(a, list):
        if not isinstance(b, list) or len(a) != len(b):
            return [p]
        return sum((walk(x, y, f"{p}[{i}]") for i, (x, y) in enumerate(zip(a, b))), [])
    return [] if a == b else [p]
diff = walk(built, ex["workflow"])
print("fields missing or changed:", len(diff), diff[:5])
print("workflow id matches the trace:", ex["workflow_id"] == saved["workflow_id"], "| agent id:", ex["agent_id"] == saved["agent_id"])
PY
```

Both lines must read `0` and `True True`. The platform adds an `agent_config` to the export; that is expected (a round
trip test on 10 October created a workflow from an export as it is, `agent_config` included, and it passed PUB-01 and
PUB-10; its leftover `firstMessage` is never spoken).

### Commit and hand in

```bash
git add final submission
git commit -m "Final build: <slot>"
git push
git rev-parse HEAD        # the commit we submit
```

Then fill `docs/submission-template.json` (copy it to `submission/submission.json`) and send the form.

### Hand-in checklist

Fill these in before Sunday; they are not known yet:

| Item | Value |
|---|---|
| Team name | `<TEAM NAME>` |
| Where to submit | `<SUBMISSION URL OR ADDRESS>` |
| Deadline | `<DATE AND TIME>` |

1. Scan the whole history for keys once more (prints counts only, never a value):

```bash
source env.sh
git log -p --all > /tmp/history.txt
grep -E -c "fak_[A-Za-z0-9]{6,}|sk-ant-[A-Za-z0-9_-]{6,}|sk-or-[A-Za-z0-9_-]{6,}|Bearer [A-Za-z0-9._-]{10,}" /tmp/history.txt   # must be 0
for v in FREYA_API_KEY FREYA_BANK_TEAM_KEY ANTHROPIC_API_KEY; do echo "$v: $(grep -F -c -- "${!v}" /tmp/history.txt)"; done   # all 0 (bash; in zsh use ${(P)v})
git log --all --name-only --format= | grep -E '(^|/)(env\.sh|\.env)$'                                                           # must print nothing
rm /tmp/history.txt
```

   If anything is found: do not make the repo public. Rotate the key first, then rewrite the history.

2. Make the repository public: GitHub, `selvataas/freya_hackhathon`, Settings, General, Danger Zone, Change visibility,
   Public. Or `gh repo edit selvataas/freya_hackhathon --visibility public --accept-visibility-change-consequences`.
3. Open the repository in a private browser window to check it can be read without a login.
4. Fill `submission/submission.json` from the template: team name, repository URL, the commit (`git rev-parse HEAD`), and
   per brief the slot, workflow id, agent id and the paths of the export, the trace and the build log.
5. Submit at the address above: the repository URL with the commit, the two `submission/<slot>.workflow.json`, the two
   traces, and the form.
6. After submitting: no more pushes to the submitted commit's branch until the organisers confirm receipt.

## 5. If something goes wrong

| What | Do |
|---|---|
| Traceback in the builder | Read it. If it is a crash on an input the parser did not expect (a table, a file type, a missing field), fix the code generally, commit, build again. Never add the brief's values, names or rules to the code or prompts. |
| `stop_reason` not `end_turn`, or `no usable spec` | Build again once. The second build costs the same again. |
| `dry_run` refused | Read the error; it names the field. Fix the template code generally, build again: the spec comes from the cache, no new cost. |
| `Workspace plan limit reached` | Delete a workflow we do not submit (spike first). Never delete Base, brief-a or brief-b without a reason. |
| Platform down (503, no answer) | Wait. The cache keeps the spec, so the next build does not pay again. |
| A self-test scenario fails | Read the problem in the trace. A runtime bug: fix generally, build again (cached, free). A spec that is wrong for the brief: build again with `--no-cache` once (paid). |
| Time is short | Submit the agent of the last good build with its own trace. One complete run beats a half-fixed one. |

A rebuild of the same brief with the same model reads the spec from `cache/` and costs nothing. `--no-cache` forces a
new extraction and costs again. `--no-llm` stops instead of calling the model: use it for rebuilds after a code fix, to be
sure nothing is spent.

## 6. Do not

- Do not write anything from a final brief into the builder, the prompts or a test: no holiday, no outcome name, no phrase.
- Do not edit a workflow on the platform, in the dashboard or with a hand-made PUT.
- Do not change `freya.py`, `AGENT_LLM` or the agent model.
- Do not commit `env.sh`, `.env` or a key. `git status` before every commit.
- Do not run `--no-cache` without a reason (it pays a new extraction).
- Do not submit a workflow and a trace from different runs.
- Do not delete `cache/` before the submission is done.

## Submission template

The official form's fields are not known to us yet; this template holds what the README asks for. Adjust the keys to
the form when it opens. A copy is in `docs/submission-template.json`.

```json
{
  "team": "",
  "contact": "",
  "repository": "https://github.com/selvataas/freya_hackhathon",
  "commit": "",
  "builder_command": "LLM_MODEL=claude-opus-5-5 python3 builder/build.py <brief>... <openapi.json>",
  "builder_model": "claude-opus-5-5",
  "agent_model": "experimental-5",
  "briefs": [
    {
      "brief": "",
      "brief_files": [],
      "tool_api_file": "",
      "slot": "",
      "workflow_id": "",
      "agent_id": "",
      "workflow_export": "submission/<slot>.workflow.json",
      "trace": "submission/<slot>.trace.jsonl",
      "build_log": "submission/<slot>.build.log",
      "build_started": "",
      "build_ended": "",
      "build_seconds": null,
      "model_calls": null,
      "selftest": "",
      "warnings": null
    },
    {
      "brief": "",
      "brief_files": [],
      "tool_api_file": "",
      "slot": "",
      "workflow_id": "",
      "agent_id": "",
      "workflow_export": "submission/<slot>.workflow.json",
      "trace": "submission/<slot>.trace.jsonl",
      "build_log": "submission/<slot>.build.log",
      "build_started": "",
      "build_ended": "",
      "build_seconds": null,
      "model_calls": null,
      "selftest": "",
      "warnings": null
    }
  ],
  "notes": ""
}
```

`build_started`, `build_ended`, `build_seconds`, `model_calls`, `selftest` and `warnings` come from the trace
(`start`, `end`, the `model_call` count, `selftest`, `end.warnings`).
