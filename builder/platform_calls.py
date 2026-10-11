"""The build's platform calls with a limited retry: the dry run, the save (a first create, or the update and publish of
a slot that exists) and the export. Only platform failures are retried (503, 504, no connection or no answer); any
other answer (a 4xx) stops at once. Every try goes into the trace.

A first create that failed may still have gone through. Before every create, the workspace is searched for a workflow
of the slot; one that is there is taken over and written to the state file. A second workflow is never made.

    python3 builder/platform_calls.py export <slot> <path>     # the export, with the same retry, into the slot's newest trace
"""
import json, os, pathlib, re, socket, sys, time, urllib.error

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
import freya

# seconds before each retry: the first after 1.5 minutes, then every 5 minutes (about 17 minutes in all)
WAITS = [float(x) for x in os.environ.get("PLATFORM_RETRY_WAITS", "90,300,300,300").split(",") if x.strip()]
BUDGET_S = 25 * 60  # no retry waits past 25 minutes after the build started, so a brief stays under 30 minutes
_deadline = [time.time() + BUDGET_S]


def start(t0):
    """Retries end BUDGET_S after t0, the start of the build."""
    _deadline[0] = t0 + BUDGET_S


def platform_error(e):
    """503, 504, no connection, no answer: the platform's trouble, worth another try. Anything else is not."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code in (503, 504)
    if isinstance(e, (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout)):
        return True
    m = re.search(r" -> (\d{3})\b", str(e)) if isinstance(e, RuntimeError) else None
    return bool(m) and m.group(1) in ("503", "504")


def attempt(trace, what, fn):
    """fn() with retries on platform failures. Every try is a 'platform_call' event in the trace."""
    for i in range(len(WAITS) + 1):
        t = time.time()
        try:
            r = fn()
            trace.event("platform_call", what=what, attempt=i + 1, result="ok", seconds=round(time.time() - t, 1))
            return r
        except Exception as e:
            err = str(e)[:300]
            if not platform_error(e):
                trace.event("platform_call", what=what, attempt=i + 1, result="stopped: not a platform failure", error=err)
                raise
            if i == len(WAITS) or time.time() + WAITS[i] > _deadline[0]:
                trace.event("platform_call", what=what, attempt=i + 1, result="gave up", error=err)
                raise
            trace.event("platform_call", what=what, attempt=i + 1, result="platform failure, will try again", error=err,
                        next_try_in_s=WAITS[i])
            time.sleep(WAITS[i])


def _state(path):
    return json.loads(path.read_text()) if path.exists() else {}


def _write_state(path, slot, ids):
    s = _state(path)
    s[slot] = ids
    path.write_text(json.dumps(s, indent=1))


def find_slot(slot):
    """The workflows of the workspace that belong to a slot: named as the slot, or as a first create names it
    ('<slot> MMDD-HHMMSS'). Newest first."""
    out, off = [], 0
    while True:
        r = freya.api("GET", "/api/v2/workflow", workspaceId=freya.workspace_id(), limit=100, offset=off)
        items = r.get("workflows") or []
        out += [w for w in items if w.get("name") == slot or re.fullmatch(re.escape(slot) + r" \d{4}-\d{6}", w.get("name") or "")]
        off += len(items)
        if not items or off >= int(r.get("total") or 0):
            break
    return sorted(out, key=lambda w: str(w.get("createdAt") or ""), reverse=True)


def save(trace, slot, wf, state_file):
    """Saves the workflow to its slot and returns {workflow_id, agent_id[, version]}. A first create looks for a
    workflow of the slot before every try and takes it over; then the slot is updated and published."""
    path = pathlib.Path(state_file)
    if slot not in _state(path):
        def create():
            found = find_slot(slot)
            if found:
                w = found[0]
                trace.event("platform_adopted", slot=slot, workflow_id=w.get("id"), name=w.get("name"), others=[x.get("id") for x in found[1:]],
                            about="the workspace already holds a workflow of this slot (a create that answered with an error went through): "
                                  "taken over, no second one made")
                _write_state(path, slot, {"workflow_id": w["id"], "agent_id": w.get("agentId")})
                return None
            ids = freya.create_workflow(f"{slot} {time.strftime('%m%d-%H%M%S')}", wf)
            _write_state(path, slot, ids)
            return ids
        ids = attempt(trace, "create", create)
        if ids:
            return ids
    return attempt(trace, "update and publish", lambda: freya.save_workflow(slot, wf, state_file=str(path)))


def export(slot, out_path, state_file=ROOT / ".freya-agents.json"):
    """The export of a slot's workflow, with the retry; the tries go into the slot's newest trace."""
    from trace import Trace
    traces = sorted((ROOT / "traces").glob(f"2*-{slot}.jsonl"))
    tr = Trace(str(traces[-1] if traces else ROOT / "traces" / f"{time.strftime('%Y%m%d-%H%M%S')}-{slot}-export.jsonl"))
    try:
        first = json.loads(open(tr.path).readline() or "{}")
        built = time.mktime(time.strptime(first["t"][:19], "%Y-%m-%dT%H:%M:%S"))
        _deadline[0] = min(time.time() + 20 * 60, built + 29 * 60)
    except Exception:
        _deadline[0] = time.time() + 20 * 60
    s = json.loads(pathlib.Path(state_file).read_text())[slot]
    try:
        p = attempt(tr, "export", lambda: freya.export_workflow(s["workflow_id"], out_path))
        tr.event("exported", slot=slot, workflow_id=s["workflow_id"], path=str(out_path))
        return p
    finally:
        tr.close()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "export":
        print(export(sys.argv[2], sys.argv[3]))
    else:
        sys.exit(__doc__)
