# Runbook: the final (Sunday evening)

**The final as the hackathon page describes it on 11 October (this section replaces sections 1 to 4 and the submission
template at the end, which were written for two briefs with their own tool API files).** One case, Freya Bank's
credit card statement-debt line, in Turkish: one zip with a folder of the bank's documents (Markdown, Word, PDF,
Excel), a service contract, the bank's test customers and six example conversations. We write a mock of the bank's
services on Cloudflare Workers, deploy it before the build and keep it running until the results are out; the phone
agent calls only the mock. Deadline 20:00 UTC (23:00 Istanbul): `submission.json` to the address in the kit email.
Sections 0 (19:30 pre-check) and 5a (platform down) still apply; read `hidden-N` there as `final`.

F1. **Get the case** at 17:00 UTC (20:00 Istanbul), from the Submit tab of the page or the e-mail. Unzip it under
    `case/`, content unchanged. The slot (the workflow's name) is the folder's name.

```bash
mkdir -p case && unzip -q <the zip> -d case && ls case     # case/<Folder>/
```

F2. **The mock** (`mock/`, generic; the final's data go only into `mock/data/`, never into `builder/`):
    - `mock/data/customers.json`: the zip's test customers as `[{customer_id, identity: {field: value}, products:
      [{product_id, ...the fields the contract's account answer has}]}]`.
    - `mock/data/config.json`: for each operation of the service contract, its `path`, its role (`verify_identity`,
      `get_account`, `create_promise`, `add_note`, `schedule_callback`, `transfer_to_agent`, `close_call`), its
      request field names (`fields`: role -> name) and response field names (`response`: role -> name), the wrong-answer
      limit (`max_wrong_total`) and the hint value for a date with day and month swapped, if the contract has one.
    - Deploy and check, then commit the mock data on its own ("Mock data for the final case"), before the build, so
      the build runs on a clean tree:

```bash
cd mock && wrangler deploy && cd ..
curl -s https://fides-mock.fides-freya.workers.dev/health          # ok, the tools, the number of customers
curl -s -X POST https://fides-mock.fides-freya.workers.dev/<verify path> -H 'content-type: application/json' -d '{...one test customer...}'
git add mock/data && git commit -m "Mock data for the final case" && git push
```

F3. **Build** with `--no-cache`, the folder and the mock's address; then export at once and keep the trace:

```bash
SLOT=<Folder>; M=https://fides-mock.fides-freya.workers.dev
python3 builder/build.py --no-cache case/$SLOT $M 2>&1 | tee traces/final.log
python3 builder/platform_calls.py export $SLOT submission/final.workflow.json
T="$(ls -t traces/2*-$SLOT.jsonl | head -1)"
cp "$T" traces/final.jsonl && cat "$T" >> traces/final.log
grep -E -c "fak_[A-Za-z0-9]{6,}|sk-ant-[A-Za-z0-9]{6,}|Bearer " traces/final.log traces/final.jsonl   # every count must be 0
```

    Check the trace as in section 3: `documents` (every file read; a skipped one is named), `contract` (which file,
    or written by the model), `model_call`s, `selftest` n/n, `dry_run`, `saved`, `end`, `git_dirty: false`. Read
    `out/$SLOT.spec.json`: `language` is `tr`, the phrases are Turkish, the outcome table and the tool fields match
    the contract. The export check of section 4 works with `submission/final.workflow.json` and `traces/final.jsonl`.
F4. **Commit and send.** The page: "Before 20:00 UTC (23:00 Istanbul), e-mail three files to `yavuz@freyavoice.ai`:
    `submission.json`, the exported workflow and the trace. Keep the same files in your repo at the commit you name."
    The three files are `submission/submission.json`, `submission/final.workflow.json` and `traces/final.log`.
    `submission.json` names a commit, so it cannot be inside that commit: the named commit holds the case, the exported
    workflow and the trace; `submission.json` follows in the next commit, on its own. Our target: sent by 22:30.

```bash
grep -E -c "fak_[A-Za-z0-9]{6,}|sk-ant-[A-Za-z0-9]{6,}|Bearer " traces/final.log traces/final.jsonl submission/final.workflow.json   # every count must be 0
git add case submission/final.workflow.json traces/final.log traces/final.jsonl
git commit -m "Final build: the case, the exported workflow and the trace" && git push
C="$(git rev-parse HEAD)"                                   # the commit we name
python3 - "$C" <<'PY'
import json, sys
t = json.load(open("docs/submission-template.json")); t["commit"] = sys.argv[1]
json.dump(t, open("submission/submission.json", "w"), indent=1, ensure_ascii=False); print(json.dumps(t, indent=1, ensure_ascii=False))
PY
git add submission/submission.json && git commit -m "submission.json for commit ${C:0:7}" && git push
git ls-tree -r --name-only "$C" submission/final.workflow.json traces/final.log   # both listed at the named commit
```

    Make the repository public (section 4, hand-in checklist steps 1, 4 and 5: key scan of the whole history first).
    Then send one e-mail to `yavuz@freyavoice.ai` with the three files attached
    (`submission/submission.json`, `submission/final.workflow.json`, `traces/final.log`), subject and body below, with
    the commit filled in. Optional: the Claude Code session logs of building the builder may be shared too.

```text
Subject: Fides – Build the Builder final submission

Hello,

Attached is our final submission for Build the Builder: submission.json, the exported workflow
(final.workflow.json) and the trace of the builder run that made it (final.log).

Team: Fides (Selva Taş, selvataas@gmail.com)
Repository: https://github.com/selvataas/freya_hackhathon
Commit: <commit>
  The exported workflow and the trace are at that commit: submission/final.workflow.json and traces/final.log.
  submission.json names that commit, so it is in the commit right after it.
Mock: https://fides-mock.fides-freya.workers.dev (Cloudflare Workers; it stays up until the results are out)
Run command: python3 builder/build.py {case_folder} {mock_url}

To run the builder: Python 3.9 or newer, no packages needed, and these environment variables:
  ANTHROPIC_API_KEY  for the builder's model calls (reading the documents and the spec)
  FREYA_API_KEY      for the Freya workspace where the phone agent is created
  FREYA_API_URL      the Freya API address (the staging address of the kit's env.example)

Thank you,
Selva Taş – team Fides
```

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

**19:30 pre-check: no simulation may be running or stuck.** Our practice tests stop at 19:30 (none starts after 19:10).
Then list the workspace's last simulations (one read, no new simulation):

```bash
python3 -c "
import freya
r = freya.api('GET', '/api/v2/simulations', limit=5)
for s in (r.get('simulations') or r.get('data') or [])[:5]: print(s.get('id'), s.get('name'), s.get('status'), s.get('createdAt'), s.get('updatedAt'))
"
```

Every one must be finished (`completed`, or another final status). A simulation still `running`, `pending` or `queued`
blocks every new simulation of the workspace, and the bank sessions of a test that waits behind it expire ("the call
is already closed"): on 11 October one stayed `running` for two hours after its run crashed on a 503. If one is open:

- If it was started less than about 15 minutes ago, wait for it, checking every 5 minutes (not more often: the platform
  is busy and every request adds to it).
- If it has not moved for longer, or the list itself answers 503/504 for more than 15 minutes, tell the organisers
  (the address in the kit email), with the simulation id, its status and since when. The builds do not need a
  simulation, so go on with section 1 meanwhile.

The builds need no simulation, but publishing and the export do need the platform: the dry run, the save and
`export_workflow` are platform calls. If the platform answers 503/504 or not at all in the evening, follow section 5a.

We keep the workspace at 10 workflows at most; the platform's limit is 200. Today: brief-a, brief-b, spike. Each final
brief adds one (`hidden-1`, `hidden-2`).

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
   `start` names the code it ran from: `git_commit` is the commit we pushed before the build (`git rev-parse HEAD`),
   `git_dirty` is `false` and `git_untracked` lists only this brief, its tool API file and the log. `git_dirty: true`
   means the build ran on uncommitted code: commit and push, then build again with `--no-cache`.
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
python3 builder/platform_calls.py export $SLOT submission/hidden-$N.workflow.json   # retried on 503/504; the tries go into the build's trace
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
# the trace names the commit the build ran from; the submitted commit adds only the brief, the export and the traces
B="$(python3 -c "import json,sys; print(json.loads(open(sys.argv[1]).readline())['git_commit'])" traces/hidden-$N.jsonl)"
git diff --stat "$B" HEAD -- builder freya.py tools   # must print nothing: same builder code
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
| Platform down (503, 504, no answer) | Section 5a. |
| A self-test scenario fails | Read the problem in the trace. A runtime bug: fix generally, check with `--dry --no-llm` (cached, free, not submitted), commit, then build again with `--no-cache`. A spec that is wrong for the brief: build again with `--no-cache`. |
| Time is short | Submit the agent of the last good build with its own trace. One complete run beats a half-fixed one. |

A build that is submitted always runs with `--no-cache`, so its trace holds the model calls that made its spec. The
cache is only for checks that are never submitted: `--dry --no-llm` rebuilds from the cached spec without any model call
and without touching the workflow on Freya.

## 5a. The platform is down in the evening

What the builder does when the platform answers 503 or 504, or not at all (`tests/test_platform_retry.py` runs each
case against a fake API):

- **It tries again**, for the dry run, the save (a first create, or the update and publish of a slot that exists) and
  the export (`builder/platform_calls.py export`): the second try 1.5 minutes after the first, then every 5 minutes,
  five tries at most, and no try waits past 25 minutes after the build started, so a brief stays under 30 minutes.
  Only 503, 504 and a missing connection or answer are tried again; any other answer (a 4xx) stops at once. Every try
  is a `platform_call` event in the trace. **Do not stop a build that is waiting**: the console shows nothing while
  it waits; the trace shows the tries.
- A first create that answered with an error may still have gone through. Before every create the builder looks for
  a workflow of the slot in the workspace (named `hidden-N` or `hidden-N <date-time>`); if there is one, it takes it
  over (`platform_adopted` in the trace), writes it to `.freya-agents.json`, and updates and publishes it. A second
  workflow is never made.
- Everything before the first platform call is done and kept: the model calls, the spec cache, the self-test,
  `out/<slot>.spec.json`, `out/<slot>.workflow.json` and the trace, which is written line by line.
- When the tries run out, the build stops with a traceback and exit code 1; the trace ends with `platform_call ...
  gave up`, `error` and `end`. If it stopped at the dry run, nothing changed on the platform. If it stopped while
  updating a slot that exists, a PUT that went through may have left a new, unpublished version; the published
  version is still the old one, and `.freya-agents.json` keeps the old version number.

What to do:

1. Build as in section 4, with `--no-cache`. The build does not need the platform until its last steps, and it
   waits out a short outage by itself.
2. **Keep the local outputs in any case**, also when the build gave up at the dry run or the save. `out/` and the
   builder's traces are not committed, so copy them under names that say they are local, then commit and push:

```bash
N=1; SLOT=hidden-$N
T="$(ls -t traces/2*-$SLOT.jsonl | head -1)"
cp out/$SLOT.workflow.json submission/$SLOT.local.workflow.json
cp out/$SLOT.spec.json submission/$SLOT.local.spec.json
cp traces/$SLOT.log traces/$SLOT.platform-down.log && cat "$T" >> traces/$SLOT.platform-down.log
cp "$T" traces/$SLOT.platform-down.jsonl
grep -E -c "fak_[A-Za-z0-9]{6,}|sk-ant-[A-Za-z0-9]{6,}|Bearer " traces/$SLOT.platform-down.log traces/$SLOT.platform-down.jsonl   # every count must be 0
git add submission/$SLOT.local.* traces/$SLOT.platform-down.* briefs/hidden-*
git commit -m "Local build output of $SLOT while the platform is down" && git push
```

3. Check the platform every 5 minutes, not more often: one chat turn as in section 0, or the simulation list of the
   19:30 pre-check.
4. **When the platform answers again: publish and export** by building again as in section 4, with `--no-cache`, and
   export at once. The new run's trace, log and export are the submitted three; the `platform-down` files stay in the
   repository as the record of the earlier run. Building again, and not publishing the earlier file, keeps the rules:
   the submitted workflow is the output of the run whose trace we submit, that run reads the brief itself, and no
   workflow is saved by hand. It costs another $0.50 to $0.80 and 2 to 3 minutes per brief.
   - A workflow left by a create that answered with an error needs nothing: the new build takes it over.
   - An unpublished version left by a failed update needs nothing: the new build saves and publishes a newer one.
5. **If the platform has not answered by 22:00 Istanbul (19:00 UTC)**, write to the organisers (the address in the
   kit email): team Fides; the briefs affected; since when the platform answers 503/504 (the `error` line of the
   trace); that the builds ran with `--no-cache` (start and end time from the trace); and that the builder's local
   output and trace are committed at `<commit>` (`submission/hidden-N.local.workflow.json`,
   `submission/hidden-N.local.spec.json`, `traces/hidden-N.platform-down.log`). Ask how they want it submitted. Put
   the local files in the form only if they say so. Keep checking every 5 minutes; if the platform answers before the
   deadline, do step 4 and submit as usual.

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
