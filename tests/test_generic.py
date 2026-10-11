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
    check(list(nodes) == ["calendar", "start_find_appointments", "main", "bye"] and wf["initial_node"] == "calendar",
          "calendar, the start lookup, the conversation, the closing node")
    start = nodes["start_find_appointments"]["pre_actions"][0]["function"]["parameters"]["properties"]
    check(start["url"]["default"] == "https://mock.example/owners/{{callerPhone}}/appointments" and start["method"]["default"] == "GET",
          "the start lookup's path parameter comes from the call variable")
    main = nodes["main"]
    names = [t["function"]["name"] for t in main["tools"]]
    check(sorted(names) == sorted(list(tools) + ["end_call"]), "every operation is a tool of the conversation, and end_call")
    move = next(t for t in main["tools"] if t["function"]["name"] == "move_appointment")["function"]["parameters"]["properties"]
    check(move["url"]["default"] == "https://mock.example/appointments/move" and move["body"]["properties"]["new_date"]["default"] == "{{new_date}}",
          "a model-filled field has a placeholder of its own name")
    check(main["transitions"][0]["target_node"] == "bye" and main["extraction_schema"][0]["name"] == "done", "the conversation closes through 'done'")
    check(nodes["bye"]["terminal"]["function"]["parameters"]["properties"]["spoken_message"]["default"] == spec["closing_line"],
          "the closing node says the closing line")
    check("{{calendar}}" in main["task_message"] and "{{start_find_appointments}}" in main["task_message"], "the briefing holds the calendar and the start lookup")
    code = nodes["calendar"]["pre_actions"][0]["function"]["parameters"]["properties"]["code"]["default"]
    env = {"vars": {"now": "2026-11-03T14:20:00+03:00"}}
    exec(code, env)
    cal = env["vars"]["calendar"]
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
