"""The ask-client layer without any API call: a fake model, the file transport, and the spec of a test brief.

    python3 tests/test_ask_client.py
"""
import copy, json, os, pathlib, shutil, sys, tempfile
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))
import ask_client


class Trace:
    def __init__(self):
        self.events = []

    def event(self, kind, **data):
        self.events.append(dict(data, event=kind))


def fake_llm(calls):
    def llm(purpose, system, user):
        calls.append(purpose)
        if "questions" in purpose:
            return {"questions": [
                {"id": "q1", "question": "Which latest promise date applies to the standard segment?", "about": "bands[0].deadline_n"},
                {"id": "q2", "question": "Is anything else different for priority customers?", "about": "bands[1].deadline_n"},
                {"id": "q3", "question": "Until what time can callbacks be booked?", "about": "third_party.window_end"}]}
        return {"changes": [
            {"path": "bands[0].deadline_n", "value": 9, "because": "q1"},
            {"path": "bands[7].deadline_n", "value": 3, "because": "q2"},
            {"path": "third_party.window_end", "value": 1800, "because": "q3"}]}
    return llm


def main():
    ok = True

    def check(cond, what):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + what)
        ok = ok and cond

    spec = None
    for f in sorted((ROOT / "cache").glob("spec-*.json")):
        d = json.load(open(f))
        if str(d.get("bank_name", "")).startswith("Halden") and (d.get("bands") or [{}])[0].get("deadline_n") == 7:
            spec = d  # the Halden2 test brief's raw spec, as extracted
    if spec is None:
        sys.exit("no cached spec of the Halden2 test brief; build tests/variants/v3/brief-halden2 once first")
    old = os.environ.pop("CLIENT_MODE", None)
    check(not ask_client.enabled(False), "off by default (no flag, no CLIENT_MODE)")
    os.environ["CLIENT_MODE"] = "1"
    check(ask_client.enabled(False), "CLIENT_MODE=1 turns it on")
    os.environ.pop("CLIENT_MODE")
    if old is not None:
        os.environ["CLIENT_MODE"] = old

    tmp = pathlib.Path(tempfile.mkdtemp())
    ask_client.CACHE = tmp  # keep the test's cache out of the real one
    transport = ask_client.FileTransport(ROOT / "tests" / "client-answers.json")
    calls, trace = [], Trace()
    out = ask_client.run(copy.deepcopy(spec), [("brief.md", "text")], transport, trace, llm=fake_llm(calls))
    qa = [e for e in trace.events if e["event"] == "client_qa"]
    check(len(qa) == 3, "three questions asked and answered")
    check("7th working day" in qa[0]["answer"], "q1 answered from the file (keyword match)")
    check(qa[1]["answer"] == transport.default, "q2 has no answer in the file: the default answer")
    check(out["bands"][0]["deadline_n"] == 9, "a valid change is applied")
    check(out["third_party"]["window_end"] == spec["third_party"]["window_end"], "a change with the wrong type is rejected by the schema")
    rejected = [e for e in trace.events if e["event"] == "client_change_rejected"]
    check(len(rejected) == 2 and any("no such path" in e["why"] for e in rejected), "a change to a path that does not exist is rejected")
    check(any(e["event"] == "client_change" and e["path"] == "bands[0].deadline_n" for e in trace.events), "the applied change is in the trace")
    check(calls == ["list unclear points of the brief as questions for the client", "fold the client's answers into the spec"], "two model calls")

    calls2, trace2 = [], Trace()
    out2 = ask_client.run(copy.deepcopy(spec), [("brief.md", "text")], transport, trace2, llm=fake_llm(calls2))
    check(calls2 == [] and out2 == out and any(e["event"] == "client_cache_hit" for e in trace2.events), "a second run reads the cache and calls nothing")

    trace3 = Trace()
    out3 = ask_client.run(copy.deepcopy(spec), [("brief.md", "text")], ask_client.FileTransport(tmp / "none.json"), trace3, llm=None, allow_llm=False, use_cache=False)
    check(out3 == spec, "--no-llm with nothing cached leaves the spec as it is")
    # keyword matching of the file transport, with the questions the real model asked on 11 October
    t = transport
    q = lambda text: {"id": "x", "question": text}
    check("7th working day" in t.ask(q("For standard-segment customers (1-14 days late), is the latest promise date the 7th working day (9 Nov email), the 12th (25 Oct pilot email) or the 10th (policy CP-7)?")),
          "several keys with the same answer: that answer (hyphen read as a space)")
    check("10:00 to 18:00" in t.ask(q("Is a 'callback today' only allowed if the requested time is later than now and before 18:00?")),
          "an 8-character key ('callback') matches")
    check(t.ask(q("If a customer in a multi-product call is transferred (e.g. to the hardship desk) after one product already has a recorded promise, what outcome should be recorded?")) == t.default,
          "a key found only inside an example is a weak match: the default answer")
    check(t.ask(q("Is the callback window different for the hardship desk?")) == t.default,
          "two keys pointing to different answers: the default answer")
    check(t.ask(q("Is the callbacks list kept?")) != t.default, "a plural of the key still matches")
    check(t.ask(q("Is there a callbackfee?")) == t.default, "a key inside another word does not match")
    shutil.rmtree(tmp)
    print("\nall passed" if ok else "\nSOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
