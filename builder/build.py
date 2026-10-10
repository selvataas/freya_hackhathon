"""Build a Freya phone agent from a bank's brief and its tool API.

    python3 builder/build.py <brief>... <openapi.json> [--no-cache] [--test A|B] [--slot NAME] [--dry]

The last positional argument is the tool API. A brief may be a folder: its files are read in name order.
Several briefs are read in order (a later brief builds on the earlier ones). The slot (the workflow this build
updates) is the last brief's file name without extension, or the folder name.
"""
import argparse, json, os, pathlib, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import freya
import openapi_tools, render
from extract import extract, check_verbatim, MODEL, EFFORT
from spec_schema import normalize
from trace import Trace


def read_briefs(paths):
    out = []
    for p in paths:
        p = pathlib.Path(p)
        files = sorted(x for x in p.iterdir() if x.is_file() and not x.name.startswith(".")) if p.is_dir() else [p]
        for f in files:
            out.append((f.name, f.read_text(errors="replace")))
    return out


def slot_name(paths):
    p = pathlib.Path(paths[-1])
    return p.name if p.is_dir() else p.stem


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--slot")
    ap.add_argument("--test", help="run the practice customers of this brief letter after the build")
    ap.add_argument("--dry", action="store_true", help="build and validate, do not save to Freya")
    a = ap.parse_args()
    if len(a.paths) < 2:
        sys.exit(__doc__)
    brief_paths, api_path = a.paths[:-1], a.paths[-1]
    slot = a.slot or slot_name(brief_paths)
    trace = Trace(str(ROOT / "traces" / f"{time.strftime('%Y%m%d-%H%M%S')}-{slot}.jsonl"))
    warnings = []
    warn = lambda m: (warnings.append(m), trace.event("warning", message=m))
    trace.event("start", briefs=brief_paths, tool_api=api_path, slot=slot, builder_model=MODEL, effort=EFFORT, agent_llm=freya.AGENT_LLM)
    try:
        briefs = read_briefs(brief_paths)
        api_text = pathlib.Path(api_path).read_text()
        _, tools = openapi_tools.load(api_path)
        trace.event("tools", names=sorted(tools))
        raw, info = extract(briefs, api_text, trace, use_cache=not a.no_cache)
        trace.event("spec", **info)
        spec = normalize(raw, tools, warn)
        check_verbatim(spec, briefs, warn)
        wf = render.render(spec, tools)
        out = ROOT / "out"
        out.mkdir(exist_ok=True)
        (out / f"{slot}.spec.json").write_text(json.dumps(spec, indent=1))
        (out / f"{slot}.workflow.json").write_text(json.dumps(wf, indent=1))
        v = freya.validate_workflow(slot, wf)
        trace.event("dry_run", result=v)
        if a.dry:
            print(json.dumps({"slot": slot, "dry_run": v, "warnings": len(warnings)}))
            return
        ids = freya.save_workflow(slot, wf, state_file=str(ROOT / ".freya-agents.json"))
        trace.event("saved", slot=slot, **ids)
        print(json.dumps({"slot": slot, **ids, "warnings": len(warnings)}))
        if a.test:
            cmd = [sys.executable, str(ROOT / "tools" / "run_cases.py"), ids["agent_id"], "--brief", a.test, "--out", str(ROOT / "results" / f"{slot}.json")]
            trace.event("test_start", command=" ".join(cmd[1:]))
            r = subprocess.run(cmd, capture_output=True, text=True)
            print(r.stdout[-6000:], r.stderr[-2000:])
            last = [l for l in r.stdout.splitlines() if " passed (" in l]
            trace.event("test_end", returncode=r.returncode, summary=last[-1] if last else "", lines=[l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL"))])
    except Exception as e:
        trace.event("error", error=repr(e))
        raise
    finally:
        trace.event("end", warnings=len(warnings))
        trace.close()


if __name__ == "__main__":
    main()
