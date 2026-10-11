# The builder

`builder/` reads a bank's collections brief and its tool API (OpenAPI) and creates a Freya phone agent from them, with
no manual step.

## How it works

1. **Tools from the API.** `openapi_tools.py` reads the seven tools, their fields and allowed values from the OpenAPI file.
   Nothing about the tools is typed by hand.
2. **Spec from the brief.** `extract.py` asks Claude to fill a fixed JSON spec (`spec_schema.py`): call variables, identity
   questions, calendar and holidays, bands and deadlines, persuasion attempts, amounts, outcome table, phrases, the brief's
   own situations, multi-product rules, and how the API names its fields. Two readings run in parallel; if they differ, a
   third call reconciles them. The spec is checked against the API (unknown values fall back to a safe default and are
   logged).
3. **Workflow from a template.** `render.py` turns the spec into a Freya workflow deterministically. A code step
   (`runtime.py`, the "brain") makes every decision: dates, holidays, business days, deadlines, amounts, attempts, the
   outcome. The bank's tools are called by the engine with values the code sets, never by the model; `close_call` runs at
   the end of the call with the outcome the code computed. The dialogue model only says lines the code built from the
   spec's phrases.
4. **Self-test.** `selftest.py` makes scenarios from the spec and runs them through the brain with a fake bank, on many
   calendar days. No model and no platform call; it takes well under a second. The result goes into the trace.
5. **Save.** The workflow is validated with a dry run and saved to its slot with `freya.save_workflow` (created the first
   time, updated and published afterwards).

The builder contains no value, rule or name from any brief. It only knows its own vocabularies (situations, date words).

## Run

```bash
python3 builder/build.py <brief>... <openapi.json>
```

- The last argument is the tool API. A brief can be a file or a folder (its files are read in name order, for raw
  material such as a mail, a policy extract, a memo and a code list). Several briefs are read in order: a later brief builds
  on the earlier ones.
- The slot (which workflow is updated) is the last brief's file name without extension, or the folder name.
- Output: one JSON line with `slot`, `workflow_id`, `agent_id`, `selftest` and `warnings`; the spec and the workflow in
  `out/<slot>.spec.json` and `out/<slot>.workflow.json`.

Options:

| Option | Meaning |
|---|---|
| `--dry` | Build and validate, do not save to Freya |
| `--no-cache` | Extract the spec again even if it is cached |
| `--no-llm` | Never call the model: stop if the spec is not in the cache |
| `--slot NAME` | Use another slot name |
| `--test A` | After the build, run the kit's practice customers of that brief letter |
| `--ask-client` | Ask the client about unclear points (also `CLIENT_MODE=1`). Off by default. With the local answer file it runs only together with `--test`; otherwise the builder skips it and writes `ask_client disabled` to the trace. Never used for a final build. |

## Requirements

- Python 3.9 or newer. No package is needed: the builder uses the standard library. If the `anthropic` package is
  installed, it is used for the model calls; otherwise the builder calls the Messages API over HTTP itself.
- Environment variables (in `env.sh`, never committed):

| Variable | For |
|---|---|
| `FREYA_API_KEY` | the Freya workspace |
| `FREYA_API_URL` | the Freya API, e.g. the staging URL from `env.example` |
| `FREYA_BANK_TEAM_KEY` | the practice bank (only for `--test` and `tools/run_cases.py`) |
| `ANTHROPIC_API_KEY` | the model calls of the spec extraction |
| `LLM_MODEL` | optional: the builder's model, default `claude-opus-5-5` |

The phone agent always runs on `freya.AGENT_LLM`; the builder never sets a model on the workflow.

## Cache

The spec is cached in `cache/spec-<key>.json`. The key covers the brief text, the tool API, the schema and prompt versions,
the model and the effort. A second build of the same brief with the same model costs nothing. `--no-cache` forces a new
extraction; `--no-llm` guarantees no model call.

## Trace

Every run writes `traces/<time>-<slot>.jsonl`, one JSON object per line: `start` (with `git_commit`, the commit the
builder runs from, `git_dirty`, whether tracked files had uncommitted changes, and the untracked files), the tools, every `model_call` (model,
purpose, tokens, seconds), the spec comparison, warnings, `rendered` (number of steps and tools), `selftest`,
`dry_run`, `saved` (workflow and agent id), and `end` (build seconds). API keys and the team key are masked before
anything is written.

## Tests

```bash
python3 builder/sim_local.py out/<slot>.spec.json [case ...] [-v] [--cases file.json]   # scripted customers, fake bank
python3 builder/selftest.py out/<slot>.spec.json                                       # spec-made scenarios, many days
python3 tools/run_cases.py <agent_id> --brief A [--reps 3] [--cases tests/realistic-cases.json]   # the platform
```

`tests/variants/` holds test briefs that are not hackathon briefs (renamed fields and enums; raw material with a memo
that changes the policy, as a folder of files and, in `v4`, as one Markdown file whose parts are not in date order),
`tests/calendar-cases.json` holds Brief A cases on other calendar days.
