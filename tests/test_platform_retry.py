"""The build against a fake Freya API: a short outage, a create that answered 504 but went through, an outage that
lasts, a 4xx answer, a failed publish of a slot that exists, and the export. No real platform and no model call: each
scenario runs the builder with --no-llm in a copy of the repository, against a fake API on localhost.

    python3 tests/test_platform_retry.py
"""
import http.server, json, os, pathlib, shutil, subprocess, sys, tempfile, threading
ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENT_LLM = {"provider": "experimental-5", "model": "experimental-5"}


class Fake:
    """The few routes the builder uses. rule(method, path, n) returns None (answer normally), a status code (fail
    without doing anything) or ('done', code) (do it, then answer with that code)."""
    def __init__(self, rule=None):
        self.rule, self.n, self.workflows, self.log = rule or (lambda m, p, n: None), 0, {}, []

    def handle(self, method, path, body):
        self.n += 1
        r = self.rule(method, path, self.n)
        if isinstance(r, int):
            self.log.append((method, path, r))
            return r, None
        code, result = self.route(method, path, body)
        if isinstance(r, tuple):
            code = r[1]
        self.log.append((method, path, code))
        return code, result

    def route(self, method, path, body):
        route, _, query = path.partition("?")
        if route == "/api/v2/workspaces":
            return 200, {"workspaces": [{"id": "ws"}]}
        if route == "/api/v2/workflow" and method == "POST":
            if "dryRun=true" in query:
                return 200, {"valid": True, "dryRun": True}
            i = len(self.workflows) + 1
            w = {"id": f"wf-{i}", "agentId": f"ag-{i}", "name": body["name"], "createdAt": f"2026-10-11T18:{i:02d}:00Z",
                 "versions": [{"id": f"v{i}-1", "versionNumber": 1, "isPublished": True}]}
            self.workflows[w["id"]] = w
            return 200, {"workflow": {k: w[k] for k in ("id", "agentId", "name")}}
        if route == "/api/v2/workflow" and method == "GET":
            ws = [{k: w[k] for k in ("id", "agentId", "name", "createdAt")} for w in self.workflows.values()]
            return 200, {"workflows": ws, "total": len(ws), "limit": 100, "offset": 0}
        parts = route.strip("/").split("/")
        if parts[:3] == ["api", "v2", "workflow"] and len(parts) == 4 and parts[3] in self.workflows:
            w = self.workflows[parts[3]]
            if method == "GET":
                return 200, {"workflow": {"id": w["id"], "agentId": w["agentId"], "name": w["name"], "workflow": {"agent_config": {"llmConfig": AGENT_LLM}}}}
            if method == "PUT":
                w["name"] = body.get("name") or w["name"]
                w["versions"].append({"id": f"{w['id']}-v{len(w['versions']) + 1}", "versionNumber": len(w["versions"]) + 1, "isPublished": False})
                return 200, {"workflow": {"id": w["id"]}}
        if parts[:4] == ["api", "v2", "versions", "workflow"] and len(parts) >= 5 and parts[4] in self.workflows:
            w = self.workflows[parts[4]]
            if method == "GET":
                return 200, {"versions": w["versions"]}
            if method == "POST" and parts[-1] == "publish":
                for v in w["versions"]:
                    v["isPublished"] = v["id"] == body["versionId"]
                return 200, {}
        return 404, None


def serve(fake):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def any(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"null")
            code, result = fake.handle(self.command, self.path, body)
            text = json.dumps({"success": True, "data": {"message": "ok", "result": result}}) if code == 200 else \
                ("error code: 504" if code == 504 else json.dumps({"success": False, "data": {"message": f"status {code}", "result": None}}))
            self.send_response(code); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(text.encode())
        do_GET = do_POST = do_PUT = any
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def repo_copy():
    d = pathlib.Path(tempfile.mkdtemp(prefix="retry-test-"))
    for x in ("builder", "tools", "briefs"):
        shutil.copytree(ROOT / x, d / x, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(ROOT / "freya.py", d)
    (d / "cache").mkdir()
    for f in (ROOT / "cache").glob("spec-*.json"):
        shutil.copy(f, d / "cache")
    # the cached Brief A spec under the key of the current prompt version, so that --no-llm finds it
    sys.path.insert(0, str(ROOT / "builder"))
    import extract
    briefs = [("brief-a.md", (ROOT / "briefs" / "brief-a.md").read_text(errors="replace"))]
    api = (ROOT / "tools" / "openapi.json").read_text()
    now, version = extract.cache_key(briefs, api), extract.PROMPT_VERSION
    for v in range(int(version), 0, -1):
        extract.PROMPT_VERSION = str(v)
        old = d / "cache" / f"spec-{extract.cache_key(briefs, api)}.json"
        if old.exists():
            shutil.copy(old, d / "cache" / f"spec-{now}.json")
            break
    extract.PROMPT_VERSION = version
    return d


def run(d, fake, *args):
    srv = serve(fake)
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "LLM_MODEL", "BUILDER_MODEL", "FREYA_BANK_TEAM_KEY")}
    env.update(FREYA_API_URL=f"http://127.0.0.1:{srv.server_address[1]}", FREYA_API_KEY="dummy-key", PLATFORM_RETRY_WAITS="0.2,0.2,0.2,0.2")
    cmd = [sys.executable, *args] if args[0].endswith(".py") and "/" in args[0] else [sys.executable, "builder/build.py", "--no-llm", *args]
    p = subprocess.run(cmd, cwd=d, env=env, capture_output=True, text=True, timeout=120)
    srv.shutdown()
    return p


def trace_events(d, slot):
    t = sorted((d / "traces").glob(f"2*-{slot}.jsonl"))[-1]
    return [json.loads(l) for l in open(t)]


def main():
    ok = True

    def check(cond, what):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + what)
        ok = ok and cond

    build = ("briefs/brief-a.md", "tools/openapi.json")
    calls = lambda ev, what: [(e["attempt"], e["result"]) for e in ev if e["event"] == "platform_call" and e["what"] == what]

    # 1. a short outage: the first two platform requests answer 503, then the platform is back
    d = repo_copy(); fake = Fake(lambda m, p, n: 503 if n <= 2 else None)
    p = run(d, fake, *build)
    ev = trace_events(d, "brief-a"); state = json.loads((d / ".freya-agents.json").read_text())
    check(p.returncode == 0 and len(fake.workflows) == 1 and state["brief-a"]["workflow_id"] == "wf-1",
          "short outage: the build ends, one workflow is created and written to the state file")
    check(calls(ev, "dry run") == [(1, "platform failure, will try again"), (2, "platform failure, will try again"), (3, "ok")],
          "short outage: every try of the dry run is in the trace")
    check(fake.workflows["wf-1"]["name"] == "brief-a", "short outage: the workflow is named as its slot")
    shutil.rmtree(d)

    # 2. the first create answers 504 but went through: it is taken over, no second workflow is made
    d = repo_copy()
    seen = {"create": 0}
    def rule(m, path, n):
        if m == "POST" and path == "/api/v2/workflow":
            seen["create"] += 1
            return ("done", 504) if seen["create"] == 1 else None
    fake = Fake(rule)
    p = run(d, fake, *build)
    ev = trace_events(d, "brief-a"); state = json.loads((d / ".freya-agents.json").read_text())
    check(p.returncode == 0 and len(fake.workflows) == 1 and seen["create"] == 1, "504 on a create that went through: no second create, one workflow")
    check(state["brief-a"]["workflow_id"] == "wf-1" and state["brief-a"].get("version") == 2, "504 on a create that went through: taken over, updated and published")
    check(any(e["event"] == "platform_adopted" and e["workflow_id"] == "wf-1" for e in ev), "504 on a create that went through: the takeover is in the trace")
    pub = [v["versionNumber"] for v in fake.workflows["wf-1"]["versions"] if v["isPublished"]]
    check(pub == [state["brief-a"]["version"]], "504 on a create that went through: the version in the state file is the published one")
    # the same slot built again: it updates the one workflow
    p = run(d, fake, *build)
    check(p.returncode == 0 and len(fake.workflows) == 1, "the next build of the slot updates the same workflow")
    shutil.rmtree(d)

    # 3. an outage that lasts: the build gives up after the last try; the local outputs and the trace are kept
    d = repo_copy(); fake = Fake(lambda m, p, n: 503)
    p = run(d, fake, *build)
    ev = trace_events(d, "brief-a")
    check(p.returncode != 0 and not (d / ".freya-agents.json").exists(), "lasting outage: the build stops, no state written")
    check(len(calls(ev, "dry run")) == 5 and calls(ev, "dry run")[-1] == (5, "gave up"), "lasting outage: five tries, the last one gives up, all in the trace")
    check((d / "out" / "brief-a.workflow.json").exists() and (d / "out" / "brief-a.spec.json").exists() and ev[-1]["event"] == "end",
          "lasting outage: out/ and the trace are kept, the trace ends with 'end'")
    shutil.rmtree(d)

    # 4. a 4xx answer stops at once
    d = repo_copy(); fake = Fake(lambda m, p, n: 400 if "dryRun=true" in p else None)
    p = run(d, fake, *build)
    ev = trace_events(d, "brief-a")
    check(p.returncode != 0 and calls(ev, "dry run") == [(1, "stopped: not a platform failure")] and len(fake.log) == 1,
          "4xx: no retry, one request, the stop is in the trace")
    shutil.rmtree(d)

    # 5. a slot that exists: the publish answers 503 once, the update and publish is tried again
    d = repo_copy(); fake = Fake()
    fake.workflows["wf-1"] = {"id": "wf-1", "agentId": "ag-1", "name": "brief-a", "createdAt": "2026-10-11T18:00:00Z",
                              "versions": [{"id": "v1-1", "versionNumber": 1, "isPublished": True}]}
    (d / ".freya-agents.json").write_text(json.dumps({"brief-a": {"workflow_id": "wf-1", "agent_id": "ag-1", "version": 1}}))
    seen = {"publish": 0}
    def rule5(m, path, n):
        if path.endswith("/publish"):
            seen["publish"] += 1
            return 503 if seen["publish"] == 1 else None
    fake.rule = rule5
    p = run(d, fake, *build)
    ev = trace_events(d, "brief-a"); state = json.loads((d / ".freya-agents.json").read_text())
    vs = fake.workflows["wf-1"]["versions"]
    check(p.returncode == 0 and len(fake.workflows) == 1 and state["brief-a"]["version"] == vs[-1]["versionNumber"] and vs[-1]["isPublished"],
          "failed publish of a slot that exists: tried again, the newest version is published and in the state file")
    check(calls(ev, "update and publish") == [(1, "platform failure, will try again"), (2, "ok")], "failed publish: both tries are in the trace")

    # 6. the export, with the same retry, into the slot's newest trace
    seen = {"get": 0}
    def rule6(m, path, n):
        if m == "GET" and path.startswith("/api/v2/workflow/wf-1"):
            seen["get"] += 1
            return 504 if seen["get"] == 1 else None
    fake.rule = rule6
    p = run(d, fake, "builder/platform_calls.py", "export", "brief-a", "exported.json")
    ev = trace_events(d, "brief-a")
    ex = json.loads((d / "exported.json").read_text()) if (d / "exported.json").exists() else {}
    check(p.returncode == 0 and ex.get("workflow_id") == "wf-1", "export: written after one 504")
    check(calls(ev, "export") == [(1, "platform failure, will try again"), (2, "ok")] and ev[-1]["event"] == "exported",
          "export: both tries and the export are in the build's trace")
    shutil.rmtree(d)

    print("\nall passed" if ok else "\nSOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
