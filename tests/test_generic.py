"""The generic path without any API call: the choice of path, the rendered workflow and its checks, from a fixed
generic spec of the synthetic clinic case (tests/variants/v7/veteriner, not a hackathon case).

    python3 tests/test_generic.py
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))
import generic, openapi_tools


def main():
    ok = True

    def check(cond, what):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + what)
        ok = ok and cond

    _, kit = openapi_tools.load(str(ROOT / "tools" / "openapi.json"))
    _, tools = openapi_tools.load(str(ROOT / "tests" / "variants" / "v7" / "veteriner" / "02-hizmetler.json"), base="https://mock.example")
    check(generic.fits_template(kit) and not generic.fits_template(tools), "the practice API takes the template, another API the generic path")
    check(tools["find_appointments"]["method"] == "GET" and tools["find_appointments"]["params"][0]["in"] == "path", "a GET operation with a path parameter")
    spec = json.load(open(ROOT / "tests" / "fixtures" / "generic-veteriner.spec.json"))
    wf = generic.render(spec, tools)
    nodes = wf["nodes"]
    check(list(nodes) == ["calendar", "start_find_appointments", "facts", "main", "bye"] and wf["initial_node"] == "calendar",
          "calendar, the start lookup, its answer as lines, the conversation, the closing node")
    fcode = nodes["facts"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    fenv = {"vars": {"start_find_appointments": json.dumps({"ok": True, "appointments": [{"pet_name": "A", "time": "10:00"}, {"pet_name": "B", "time": "11:30"}]})}}
    exec(fcode, fenv)
    check(fenv["vars"]["start_find_appointments_text"].splitlines() == ["ok: True", "appointments > #1 pet_name: A; time: 10:00", "appointments > #2 pet_name: B; time: 11:30"],
          "a start answer becomes one line per record")
    start = nodes["start_find_appointments"]["pre_actions"][0]["function"]["parameters"]["properties"]
    check(start["url"]["default"] == "https://mock.example/owners/{{callerPhone}}/appointments" and start["method"]["default"] == "GET",
          "the start lookup's path parameter comes from the call variable")
    main = nodes["main"]
    names = [t["function"]["name"] for t in main["tools"]]
    check(sorted(names) == sorted(list(tools) + (["end_the_call"] if spec.get("end_lines") else []) + ["end_call"]), "every operation is a tool of the conversation, and the ending tools")
    move = next(t for t in main["tools"] if t["function"]["name"] == "move_appointment")["function"]["parameters"]["properties"]
    check(move["url"]["default"] == "https://mock.example/appointments/move" and move["body"]["properties"]["new_date"]["default"] == "{{new_date}}",
          "a model-filled field has a placeholder of its own name")
    check([t["target_node"] for t in main["transitions"]] == ["bye", "bye"] and main["extraction_schema"][0]["name"] == "done", "the conversation closes through end_now or 'done'")
    check(nodes["bye"]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"] == "{{ending}}",
          "the closing node says the chosen ending")
    check("{{calendar}}" in main["task_message"] and "{{start_find_appointments_text}}" in main["task_message"], "the briefing holds the calendar and the start lookup")
    code = nodes["calendar"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    env = {"vars": {"now": "2026-11-03T14:20:00+03:00"}}
    exec(code, env)
    cal = env["vars"]["calendar"]
    check(env["vars"]["ending"] == spec["closing_line"] and env["vars"]["end_now"] == "no", "the calendar step sets the default ending")
    check("2026-11-03 Salı (today), this week" in cal and "2026-11-06 Cuma, this week" in cal and "2026-11-13 Cuma, next week" in cal,
          "the calendar names today, this week's and next week's days in the call's language")
    res = generic.check(spec, tools, wf)
    check(all(r["pass"] for r in res), f"the generic checks: {sum(r['pass'] for r in res)}/{len(res)}")
    bad = dict(spec, tools=[t for t in spec["tools"] if t["name"] != "free_slots"])
    check(not all(r["pass"] for r in generic.check(bad, tools, generic.render(bad, tools))), "a spec that leaves out an operation fails the checks")
    print("\nall passed" if ok else "\nSOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
