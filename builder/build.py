"""Build a Freya phone agent from a bank's brief and its tool API.

    python3 builder/build.py <brief>... <openapi.json> [--no-cache] [--test A|B] [--slot NAME] [--dry]
    python3 builder/build.py <case_folder> <mock_url> [...]

The last positional argument is the tool API, or the address of the mock of the bank's services: then the service
contract is read from the case folder and every tool calls the mock. A brief may be a folder: its files are read in
name order, sub-folders too (.md and text as they are, .docx and .xlsx with the standard library, .pdf by the model).
Several briefs are read in order (a later brief builds on the earlier ones). The slot (the workflow this build
updates) is the last brief's file name without extension, or the folder name.
"""
import argparse, json, os, pathlib, re, subprocess, sys, time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import freya
import ask_client, documents, generic, openapi_tools, platform_calls, render, selftest
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


def git_state():
    """The commit the builder runs from and whether tracked files differ from it; untracked files are listed apart.
    Never stops the build: without git the fields are None."""
    try:
        git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True, timeout=10, check=True).stdout
        changed = [l[3:] for l in git("status", "--porcelain", "--untracked-files=no").splitlines()]
        untracked = [l[3:] for l in git("status", "--porcelain", "--untracked-files=all").splitlines() if l.startswith("??")]
        return {"git_commit": git("rev-parse", "HEAD").strip(), "git_dirty": bool(changed), "git_changed": changed[:20],
                "git_untracked": untracked[:20]}
    except Exception as e:
        return {"git_commit": None, "git_dirty": None, "git_error": repr(e)[:200]}


def rename(workflow_id, name, wf, trace):
    """Keep the workflow's name equal to its slot. A failure here is logged and never stops the build."""
    try:
        cur = freya.api("GET", f"/api/v2/workflow/{workflow_id}", workspaceId=freya.workspace_id())["workflow"]
        if cur.get("name") != name:
            freya.api("PUT", f"/api/v2/workflow/{workflow_id}", {"name": name, "workflow": wf})
            trace.event("renamed", workflow_id=workflow_id, old=cur.get("name"), new=name)
    except Exception as e:
        trace.event("warning", message=f"could not rename the workflow: {e}"[:300])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="never call the model: stop if the spec is not in the cache")
    ap.add_argument("--slot")
    ap.add_argument("--test", help="run the practice customers of this brief letter after the build")
    ap.add_argument("--dry", action="store_true", help="build and validate, do not save to Freya")
    ap.add_argument("--ask-client", action="store_true", help="ask the client about unclear points (also CLIENT_MODE=1); off by default, refused without --test")
    ap.add_argument("--client-answers", default=os.environ.get("CLIENT_ANSWERS", str(ROOT / "tests" / "client-answers.json")),
                    help="the file transport's fixed answers")
    a = ap.parse_args()
    if len(a.paths) < 2:
        sys.exit(__doc__)
    brief_paths, api_path = a.paths[:-1], a.paths[-1]
    mock_url = api_path if re.match(r"^https?://", api_path) else None
    slot = a.slot or slot_name(brief_paths)
    trace = Trace(str(ROOT / "traces" / f"{time.strftime('%Y%m%d-%H%M%S')}-{slot}.jsonl"))
    warnings = []
    warn = lambda m: (warnings.append(m), trace.event("warning", message=m))
    trace.event("start", briefs=brief_paths, tool_api=None if mock_url else api_path, mock_url=mock_url, slot=slot, builder_model=MODEL, effort=EFFORT, agent_llm=freya.AGENT_LLM,
                **git_state())
    try:
        docs = documents.read(brief_paths, trace, allow_llm=not a.no_llm, use_cache=not a.no_cache)
        if mock_url:
            api_path = documents.contract(docs, trace, allow_llm=not a.no_llm, use_cache=not a.no_cache)
        briefs = [(n, t) for n, t, p in docs if p.resolve() != pathlib.Path(api_path).resolve()]
        api_text = pathlib.Path(api_path).read_text()
        _, tools = openapi_tools.load(api_path, base=mock_url)
        trace.event("tools", names=sorted(tools))
        if not generic.fits_template(tools):
            tools = generic.business_tools(tools)
            # a call the collections template does not fit: the generic path
            trace.event("path", mode="generic", about="the tool API lacks the collections template's tools; one dialogue step holds the API's operations")
            spec, info = generic.extract(briefs, api_text, tools, trace, use_cache=not a.no_cache, allow_llm=not a.no_llm)
            trace.event("spec", **info)
            wf = generic.render(spec, tools)
            main = wf["nodes"]["main"]
            trace.event("rendered", nodes=len(wf["nodes"]), node_types={"code": 1, "conversation": 1}, tools=len(main["tools"]),
                        tool_names=[t["function"]["name"] for t in main["tools"]], instructions_chars=len(main["task_message"]))
            t0 = time.time()
            st = generic.check(spec, tools, wf)
            ok = sum(r["pass"] for r in st)
            trace.event("selftest", about="the generic path's checks of the spec and the workflow, no model or platform call", passed=ok, total=len(st),
                        seconds=round(time.time() - t0, 1), results=st)
            if ok < len(st):
                warn(f"self-test: {len(st) - ok} of {len(st)} checks failed")
        else:
            raw, info = extract(briefs, api_text, trace, use_cache=not a.no_cache, allow_llm=not a.no_llm)
            trace.event("spec", **info)
            if ask_client.enabled(a.ask_client):
                transport = ask_client.FileTransport(a.client_answers)
                why = ask_client.refusal(transport, testing=bool(a.test))
                if why:
                    trace.event("ask_client disabled", reason=why)
                    print(f"ask_client disabled: {why}", file=sys.stderr)
                else:
                    raw = ask_client.run(raw, briefs, transport, trace, allow_llm=not a.no_llm, use_cache=not a.no_cache)
            spec = normalize(raw, tools, warn)
            check_verbatim(spec, briefs, warn)
            spec, neutral = render.neutral_phrases(spec)
            if neutral:
                trace.event("phrases_neutralized", about="success words removed from non-verbatim lines said before any result", changes=neutral)
            spec, lines = render.customer_lines(spec)
            if lines:
                trace.event("lines_for_customer", about="lines written as instructions to the agent, turned into lines for the customer", changes=lines)
            wf = render.render(spec, tools)
            kinds = {}
            for n in wf["nodes"].values():
                kinds[n["node_type"]] = kinds.get(n["node_type"], 0) + 1
            bank_tools = sorted(set([a["function"]["name"] for n in wf["nodes"].values() for a in n.get("pre_actions", []) if a["function"]["handler"] == "__function__:api_call"]
                                    + [t["function"]["name"] for t in wf.get("tools", [])]))
            trace.event("rendered", nodes=len(wf["nodes"]), node_types=kinds, tools=len(bank_tools), tool_names=bank_tools,
                        custom_situations=len(spec.get("custom_situations") or []), unplaced_rules=len(spec.get("unplaced_rules") or []))
            t0 = time.time()
            st = selftest.run(spec)
            ok = sum(r["pass"] for r in st)
            trace.event("selftest", about="local scenarios from the spec, fake bank, no model or platform call", passed=ok, total=len(st),
                        seconds=round(time.time() - t0, 1), results=[{"name": r["name"], "pass": r["pass"], "problems": r["problems"][:3]} for r in st])
            if ok < len(st):
                warn(f"self-test: {len(st) - ok} of {len(st)} scenarios failed")
        out = ROOT / "out"
        out.mkdir(exist_ok=True)
        (out / f"{slot}.spec.json").write_text(json.dumps(spec, indent=1))
        (out / f"{slot}.workflow.json").write_text(json.dumps(wf, indent=1))
        # A dry run also checks that the name is free: under the slot's own name it fails with 409 once the slot's
        # workflow exists, so every rebuild would stop here. A dry run creates nothing, so this name never exists.
        platform_calls.start(trace.t0)
        v = platform_calls.attempt(trace, "dry run", lambda: freya.validate_workflow(f"{slot} dry run", wf))
        trace.event("dry_run", result=v)
        if a.dry:
            print(json.dumps({"slot": slot, "dry_run": v, "selftest": f"{ok}/{len(st)}", "warnings": len(warnings)}))
            return
        state_file = ROOT / ".freya-agents.json"
        known = (json.loads(state_file.read_text()) if state_file.exists() else {}).get(slot)
        if known:
            rename(known["workflow_id"], slot, wf, trace)
        ids = platform_calls.save(trace, slot, wf, state_file)
        if not known:
            rename(ids["workflow_id"], slot, wf, trace)
        trace.event("saved", slot=slot, name=slot, **ids)
        print(json.dumps({"slot": slot, **ids, "selftest": f"{ok}/{len(st)}", "warnings": len(warnings)}))
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
        trace.event("end", warnings=len(warnings), build_seconds=round(time.time() - trace.t0, 1))
        trace.close()


if __name__ == "__main__":
    main()
