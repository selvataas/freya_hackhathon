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
unset LLM_MODEL BUILDER_MODEL                # the builder then uses its default, claude-opus-5-5
unset CLIENT_MODE CLIENT_ANSWERS             # ask_client stays off in the final
python3 --version                          # 3.9 or newer; no packages needed
python3 -c "import sys; sys.path.insert(0,'builder'); import extract; print(extract.MODEL)"   # claude-opus-5-5
```

Check the budget (it must leave at least $3 for the two briefs; one brief costs about $0.50 to $0.80):

```bash
python3 - <<'EOF'
import json, glob
P = {"claude-opus-5-5": (4, 20), "claude-sonnet-5-5": (2, 10)}
t = 0
for f in glob.glob("traces/2*.jsonl"):   # the builder's own traces, not the hidden-N copies
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

**After 20:00 Istanbul (17:00 UTC), check the FAQ tab of https://www.freyavoice.ai/hackathon** before the first build,
and again before submitting. The organisers answer questions there. Read the answers, but **never write a FAQ
clarification into the builder's code or prompts**: like the briefs themselves, it is about the final briefs, and
nothing from them may go into the builder. A FAQ answer can change how we run the steps of this runbook, never what the
builder contains.

**Each final brief is one Markdown file**, with its own tool API file next to it (FAQ: "Each hidden brief is one Markdown
file ... {brief_path} is that one file"). The raw-material brief too: its mail, policy extract, memo and code list are all
in that one file. Save both files under the names of the page's example command, content unchanged:

```
briefs/
  hidden-1.md               # the first final brief, one file
  hidden-1.openapi.json     # its tool API
  hidden-2.md
  hidden-2.openapi.json
```

- The slot (the workflow name) is the brief file name without extension: `hidden-1`, `hidden-2`. Neither clashes with
  `brief-a`, `brief-b` or `spike`.
- Rename the files only; never edit the content.
- In one file the order of the parts says nothing: a memo can stand before the policy it changes. The builder takes the
  rule with the latest date (tested on `tests/variants/v4/brief-halden3.md`, a raw-material brief in one file).
- If a final brief says it builds on another brief, pass both, in order (as `brief-a.md brief-b.md`).

**Fallback, if a brief does arrive as several files:** put them in one folder `briefs/hidden-N/` and pass the folder; the
builder reads every file in it in name order. Name the files so that name order is reading order (a memo after the
policy it changes), do not edit the content, and keep the tool API file outside the folder (`briefs/hidden-N.openapi.json`):
a brief folder is read whole, every file as brief text.

## 2. Build

Use plain `python3`, Opus, `--no-cache`, no `--no-llm`, and keep the console output with `tee`.

**Every build whose agent we submit runs with `--no-cache`**, the first one and every rebuild after a fix. The spec is
then read from the brief in this run, and every model call that made it is in this run's trace. A build from the cache
has no model call in its trace, and the organisers' rerun has no cache. A build costs about $0.50 to $0.80 and takes 2 to
3 minutes, well inside 30 minutes.

The first final brief is `hidden-1`, the second `hidden-2`: the same name for the slot, the brief file and the submitted
files.

```bash
mkdir -p traces submission
python3 builder/build.py --no-cache briefs/hidden-1.md briefs/hidden-1.openapi.json 2>&1 | tee traces/hidden-1.log
python3 builder/build.py --no-cache briefs/hidden-2.md briefs/hidden-2.openapi.json 2>&1 | tee traces/hidden-2.log
```

(Fallback for a brief that came as several files: `briefs/hidden-N` in place of `briefs/hidden-N.md`.)

The last line is JSON: `{"slot", "workflow_id", "agent_id", "selftest", "warnings"}`. The builder's trace is the newest
`traces/<time>-<slot>.jsonl`. Section 4 turns both into the two submitted trace files of each brief:

| File | What is in it |
|---|---|
| `traces/hidden-N.log` | The official trace: the build's console output, then the builder's whole trace, one JSON object per line |
| `traces/hidden-N.jsonl` | The builder's trace alone, unchanged, for machine reading |

Only these two names are committed from `traces/`; `.gitignore` keeps every other trace out.

## 2a. Testing during the final window (20:00 to 23:00 Istanbul, 17:00 to 20:00 UTC)

Platform tests may be limited or slow while every team runs simulations at once (one simulation at a time per
workspace; a ten-customer run took up to 8 minutes per run on a busy evening). So:

1. Rely first on what runs locally and costs nothing: the build's own self-test (in the trace, every scenario on many
   calendar days) and, if useful, `python3 builder/selftest.py out/<slot>.spec.json`.
2. There are no practice customers for a final brief, so `run_cases.py` cannot score it. A platform check is only a last
   look: one chat turn to see the workflow starts, and, if there is time, a few calls with the practice customers of the
   kit run against the new agent only when the final brief is close enough for their checks to make sense.
3. Never wait for a platform test before exporting and committing a good build. Export first; test after.
4. **The chat API skips the setup code step.** `POST /api/v2/chat/message` does not run the workflow's first code step
   (the setup), as the spike showed. A chat test can therefore show an error even when the agent is right. A chat
   result alone is never a reason to change the builder. The real assurance is the local self-test.

## 3. Checks after each build

The checks read the builder's own trace of this run:

```bash
T="$(ls -t traces/2*-hidden-N.jsonl | head -1)"   # N = 1 or 2
```

1. The last line has a `workflow_id` and an `agent_id`. A traceback means a crash: see section 5.
2. `selftest` is `n/n`. A failed scenario is listed in the trace (`event: selftest`); read it before going on.
3. `warnings`: every warning is in the trace (`event: warning`). Most are harmless (an unknown value fell back to a safe
   default). Read each one.
4. The trace has: `start`, every `model_call` (model, purpose, tokens), `spec_compare`, `rendered` (nodes, tools),
   `selftest`, `dry_run` (valid), `saved` (workflow and agent id), `end` (build_seconds).
   It has no `spec_cache_hit`: a submitted build reads its spec from the brief, with `--no-cache`.
5. **ask_client is never turned on in the final**: no `--ask-client`, no `CLIENT_MODE`. The trace must have no
   `client_` event:

```bash
grep -c '"event": "client_' "$T"   # must be 0
grep -c 'ask_client disabled' "$T"  # 0; 1 means CLIENT_MODE was set: the layer did not run, unset it anyway
```

   The builder also guards this itself: with a local answer file and no `--test`, it refuses to run the layer and
   writes `ask_client disabled` to the trace.
6. Read `out/<slot>.spec.json` against the brief. Reading is allowed, changing is not. Look at:
   call variable names, identity questions and wrong-answer limit, holidays, bands and deadlines, persuasion attempts,
   floor fields, outcome rows (`outcomes`), `custom_situations`, `unplaced_rules` (short or empty is normal),
   and for raw material: was every change of the memo applied.
7. No key in the trace or the log:

```bash
grep -E -c "fak_[A-Za-z0-9]{6,}|sk-ant-[A-Za-z0-9]{6,}|Bearer " "$T" traces/hidden-N.log   # every count must be 0
```

8. Optional, if time is left: one chat turn against the new workflow to see the opening line (a chat skips the first code
   step, so only use it to see that the workflow starts).

## 4. Export, commit, submit

**Export right after every build**, before anything else touches the workflow. The submitted workflow must be the output
of the run whose trace we submit:

- If the builder runs again for a brief (a fix, a rebuild), the new run's two trace files and its export replace the old
  three together. Never mix a trace of one run with the export of another.
- The check below must pass for the three files of each brief: `traces/hidden-N.log`, `traces/hidden-N.jsonl` and
  `submission/hidden-N.workflow.json`.

```bash
N=1; SLOT=hidden-$N       # N=2 for the second final brief
# run the build, then export at once
python3 builder/build.py --no-cache briefs/hidden-$N.md briefs/hidden-$N.openapi.json 2>&1 | tee traces/hidden-$N.log
python3 -c "import freya,json,sys; s=json.load(open('.freya-agents.json'))[sys.argv[1]]; print(freya.export_workflow(s['workflow_id'], sys.argv[2]))" $SLOT submission/hidden-$N.workflow.json
T="$(ls -t traces/2*-$SLOT.jsonl | head -1)"
cp "$T" traces/hidden-$N.jsonl
cat "$T" >> traces/hidden-$N.log          # the official trace: console output, then the whole trace
grep -E -c "fak_[A-Za-z0-9]{6,}|sk-ant-[A-Za-z0-9]{6,}|Bearer " traces/hidden-$N.log traces/hidden-$N.jsonl   # every count must be 0

# the export is this run's workflow: every field of the build output is in it, and the ids match the trace
python3 - $N $SLOT <<'PY'
import json, sys
n, slot = sys.argv[1], sys.argv[2]
ex = json.load(open(f"submission/hidden-{n}.workflow.json"))
built = json.load(open(f"out/{slot}.workflow.json"))
saved = [json.loads(l) for l in open(f"traces/hidden-{n}.jsonl") if '"event": "saved"' in l][-1]
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
git add briefs/hidden-* submission traces/hidden-*.log traces/hidden-*.jsonl
git commit -m "Final build: hidden-$N"
git push
git ls-files traces/hidden-1.log traces/hidden-1.jsonl traces/hidden-2.log traces/hidden-2.jsonl   # each submitted brief's two trace files must be listed
git rev-parse HEAD        # the commit we submit
```

Then fill `docs/submission-template.json` (copy it to `submission/submission.json`) and send the form.

### Hand-in checklist

| Item | Value |
|---|---|
| Team name | Fides |
| Where to submit | Comes in the organisers' email with the submission steps (the kit email). |
| Deadline | 20:00 UTC = 23:00 Istanbul, Sunday 11 October. Our target: everything sent by 22:00 Istanbul (19:00 UTC). |

The repository stays private until step 4, right before the form is sent.

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

2. The last build commit is pushed. Fill `submission/submission.json` from the template: the commit
   (`git rev-parse HEAD`). The team name, the repo, the run command and the paths are already in it. This file is the form's content;
   it is not committed, since it holds the commit's own id.
3. Check that the submitted commit holds the four files the form points to:

```bash
git ls-tree -r --name-only HEAD submission/hidden-1.workflow.json submission/hidden-2.workflow.json traces/hidden-1.log traces/hidden-2.log   # all four listed
```

4. Right before sending the form, make the repository public: GitHub, `selvataas/freya_hackhathon`, Settings, General,
   Danger Zone, Change visibility, Public. Or
   `gh repo edit selvataas/freya_hackhathon --visibility public --accept-visibility-change-consequences`.
5. Open the repository in a private browser window to check it can be read without a login.
6. Send the form at the address from the organisers' email, before 23:00 Istanbul (target 22:00).
7. After submitting: no more pushes to the submitted commit's branch until the organisers confirm receipt.

## 5. If something goes wrong

| What | Do |
|---|---|
| Traceback in the builder | Read it. If it is a crash on an input the parser did not expect (a table, a file type, a missing field), fix the code generally, commit, build again. Never add the brief's values, names or rules to the code or prompts. |
| `stop_reason` not `end_turn`, or `no usable spec` | Build again once, with `--no-cache`. The second build costs the same again. |
| `dry_run` refused | Read the error; it names the field. Fix the template code generally, commit, build again with `--no-cache`. To check the fix first without cost, `--dry --no-llm` reads the cached spec; that run is never submitted. |
| `Workspace plan limit reached` | Delete a workflow we do not submit (spike first). Never delete Base, brief-a or brief-b without a reason. |
| Platform down (503, no answer) | Wait, then build again with `--no-cache`. |
| A self-test scenario fails | Read the problem in the trace. A runtime bug: fix generally, check with `--dry --no-llm` (cached, free, not submitted), commit, then build again with `--no-cache`. A spec that is wrong for the brief: build again with `--no-cache`. |
| Time is short | Submit the agent of the last good build with its own trace. One complete run beats a half-fixed one. |

A build that is submitted always runs with `--no-cache`, so its trace holds the model calls that made its spec. The
cache is only for checks that are never submitted: `--dry --no-llm` rebuilds from the cached spec without any model call
and without touching the workflow on Freya.

## 6. Do not

- Do not write anything from a final brief into the builder, the prompts or a test: no holiday, no outcome name, no phrase.
- Do not edit a workflow on the platform, in the dashboard or with a hand-made PUT.
- Do not change `freya.py`, `AGENT_LLM` or the agent model.
- Do not turn on ask_client (`--ask-client`, `CLIENT_MODE`) for a final build.
- Do not write a FAQ clarification into the builder's code or prompts.
- Do not commit `env.sh`, `.env` or a key. `git status` before every commit.
- Do not submit a build that read its spec from the cache (`spec_cache_hit` in its trace). Submitted builds run with `--no-cache`.
- Do not submit a workflow and a trace from different runs.
- Do not delete `cache/` before the submission is done: the free `--dry --no-llm` checks need it.

## Submission template

The official form's fields, exactly as the hackathon page lists them. A copy is in `docs/submission-template.json`.

```json
{
  "team": "Fides",
  "repo": "https://github.com/selvataas/freya_hackhathon",
  "commit": "",
  "run_command": "python3 builder/build.py {brief_path} {tool_api_path}",
  "workflows": {
    "hidden-1": "submission/hidden-1.workflow.json",
    "hidden-2": "submission/hidden-2.workflow.json"
  },
  "traces": {
    "hidden-1": "traces/hidden-1.log",
    "hidden-2": "traces/hidden-2.log"
  }
}
```

- `team`: the team name, Fides. `commit`: the output of `git rev-parse HEAD` after the last push.
- `run_command` is the page's command as it is. The organisers fill in the two paths.
- `workflows` and `traces` point to files in the submitted commit; `git ls-files` must list all four.
