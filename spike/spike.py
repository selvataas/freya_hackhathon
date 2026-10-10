"""Spike: check talk -> code -> talk in one turn, an engine-run api_request with a post-hook,
and close_call at end_of_call with fixed values. Measures latency per turn.

    source env.sh && python3 spike/spike.py chat|sim
"""
import json, pathlib, sys, time
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
import freya
from score import http

MOCK = "https://freya-bank-mock.freyavoice.workers.dev/v1"


def api_tool(name, body_props, post=""):
    t = {"type": "function", "config": {"timeoutMs": 12000, "maxRetries": 0},
         "function": {"name": name, "handler": "__function__:api_call", "description": name,
                      "parameters": {"type": "object", "properties": {
                          "url": {"type": "string", "default": f"{MOCK}/{name}"},
                          "method": {"type": "string", "default": "POST"},
                          "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                          "body": {"type": "object", "properties": body_props, "required": []}}}}}
    if post: t["post_process_code"] = post
    return t


def code_node(name, code, transitions):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": transitions[-1]["target_node"],
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                             "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code},
                                                                              "timeout_ms": {"type": "number", "default": 10000}}}}}],
            "transitions": transitions}


def eq(var, val, target):
    return {"target_node": target, "description": f"{var} is {val}",
            "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": val}]}}


ALWAYS = lambda t: {"target_node": t, "description": "always", "condition": {"operator": "always"}}

SETUP = """
try:
    vars['turn_n'] = '0'
    vars['next_step'] = 'talk'
    vars['final_outcome'] = 'not_reached'
    vars['final_reason'] = 'unclear'
    vars['probe_state'] = 'none'
    vars['next_instruction'] = 'Greet the customer and ask for their favourite colour.'
    vars['setup_ran'] = 'yes'
except Exception:
    pass
"""

DECIDE = """
try:
    n = int(str(vars.get('turn_n') or '0')) + 1
    vars['turn_n'] = str(n)
    colour = str(vars.get('colour') or '').strip()
    vars['colour'] = ''
    probe = str(vars.get('probe_state') or 'none')
    if n == 2 and probe == 'none':
        vars['probe_field'] = 'phone_last4'
        vars['probe_answer'] = '0000'
        vars['next_step'] = 'probe'
    elif n >= 3:
        vars['final_outcome'] = 'no_promise'
        vars['final_reason'] = 'refused'
        vars['next_step'] = 'bye'
    else:
        vars['next_step'] = 'talk'
    vars['next_instruction'] = 'Say exactly: "Turn ' + str(n) + ', colour ' + (colour or 'unknown') + ', probe ' + probe + '." Then ask for another colour.'
except Exception as e:
    vars['next_step'] = 'talk'
    vars['next_instruction'] = 'Say: code error ' + str(e)[:80]
"""

AFTER_PROBE = """
try:
    v = str(vars.get('probe_verified') or vars.get('verify_identity_response.data.verified') or 'missing')
    vars['probe_state'] = 'verified_' + v
    vars['next_step'] = 'talk'
    vars['next_instruction'] = 'Say exactly: "Probe returned ' + v + ', hint ' + str(vars.get('probe_hint') or 'none') + '." Then ask for another colour.'
except Exception as e:
    vars['next_step'] = 'talk'
    vars['next_instruction'] = 'Say: probe code error ' + str(e)[:80]
"""

POST = """
try:
    if isinstance(result, dict):
        result.pop('header', None)
        d = result.get('data')
        if isinstance(d, dict):
            d['what_to_do_next'] = 'Spike: the check ran. Follow your current task.'
            try:
                vars['probe_hint'] = 'posthook_wrote_this'
            except Exception:
                pass
except Exception:
    pass
"""


def workflow():
    return {
        "initial_node": "setup",
        "system_prompt": "You are a test assistant. Speak English. One or two short sentences per turn. Never call a tool.",
        "global_nodes": {},
        "test_variables": {"customer_id": "c_test", "now": "2026-10-14T11:00"},
        "nodes": {
            "setup": code_node("setup", SETUP, [ALWAYS("talk")]),
            "talk": {"name": "talk", "node_type": "conversation", "on_enter": {"type": "llm"},
                     "task_message": "{{next_instruction}}\nNo tool call is allowed in this step.",
                     "extraction_schema": [{"name": "colour", "type": "string", "description": "The colour the user just named. Empty if none.", "min_confidence": 0.5}],
                     "max_node_turns": 40, "tools": [], "transitions": [ALWAYS("decide")]},
            "decide": code_node("decide", DECIDE, [eq("next_step", "probe", "probe"), eq("next_step", "bye", "bye"), ALWAYS("talk")]),
            "probe": {"name": "probe", "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "after_probe",
                      "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                      "pre_actions": [api_tool("verify_identity", {
                          "customer_id": {"type": "string", "default": "{{customer_id}}"},
                          "field": {"type": "string", "default": "{{probe_field}}"},
                          "answer": {"type": "string", "default": "{{probe_answer}}"}}, POST)],
                      "response_mapping": [{"path": "data.verified", "variable": "probe_verified"}],
                      "transitions": [ALWAYS("after_probe")]},
            "after_probe": code_node("after_probe", AFTER_PROBE, [ALWAYS("talk")]),
            "bye": {"name": "bye", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
                    "terminal": {"type": "function", "function": {"name": "spike_done", "handler": "__function__:end_call",
                                 "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "custom"},
                                                                                 "spoken_message": {"type": "string", "default": "Thank you, goodbye."}}}}}},
        },
        "tools": [dict(api_tool("close_call", {
            "customer_id": {"type": "string", "default": "{{customer_id}}"},
            "outcome": {"type": "string", "default": "{{final_outcome}}"},
            "reason": {"type": "string", "default": "{{final_reason}}"}}),
            config={"timeoutMs": 12000, "maxRetries": 0, "alwaysRunsAt": ["end_of_call"]})],
    }


def session():
    return http("/v1/practice/sessions", {"case": "PUB-01"})["variables"]


def chat(wf_id):
    v = session(); print("customer", v["customer_id"])
    turns, call_id = ["Hello?", "Blue.", "Green.", "Red.", "Yellow."], None
    for msg in turns:
        t0 = time.time()
        body = {"workflowId": wf_id, "message": msg, "customerVariables": v}
        if call_id: body["callId"] = call_id
        r = freya.api("POST", "/api/v2/chat/message", body)
        call_id = r.get("callId") or call_id
        print(f"[{time.time() - t0:5.1f}s] USER {msg!r}\n         AGENT {r.get('response')!r}")
        if r.get("ended") or r.get("callEnded"): break
    try: freya.api("POST", "/api/v2/chat/end", {"callId": call_id})
    except RuntimeError as e: print("end:", str(e)[:200])
    return call_id, v["customer_id"]


def report(call_id, customer_id):
    time.sleep(8)
    c = freya.get_call(call_id)
    print("endedReason:", c.get("endedReason"))
    for m in c.get("messages", []):
        role, t = m.get("role"), m.get("secondsFromStart")
        if role == "system":
            try: e = json.loads(m["message"])
            except Exception: continue
            ev = e.get("event")
            if ev == "node_enter": print(f"  {t}  node_enter {e.get('from_node')} -> {e.get('node')}")
            elif ev in ("function_call_complete",): print(f"  {t}  {ev} {e.get('function')} {json.dumps(e.get('result'))[:220]}")
            elif ev == "error": print(f"  {t}  ERROR {json.dumps(e)[:300]}")
        else:
            print(f"  {t}  {role}: {str(m.get('message'))[:120]}")
    led = http("/v1/practice/ledger/" + customer_id)
    print("ledger outcome:", led.get("outcome"), led.get("reason"), "calls:", [(x["tool"], x.get("args") or x.get("body")) for x in led["calls"]])


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "chat"
    wf = workflow()
    print("dry run:", json.dumps(freya.validate_workflow("spike", wf))[:300])
    ids = freya.save_workflow("spike", wf); print(ids)
    if mode == "chat":
        report(*chat(ids["workflow_id"]))
    else:
        p = freya.create_personas([{"name": "spike colours", "prompt": "You answer a test call. When asked for a colour, name one colour, a different one each time. When the caller says goodbye, say 'Thank you, goodbye.' and nothing more.", "successCriteria": "The call ended.", "tags": ["spike"]}])["personas"][0]["id"]
        v = session(); t0 = time.time()
        sim, it, status = freya.run_simulation(ids["agent_id"], "spike", {p: v}, max_seconds=240, concurrency=1)
        print("sim", status, f"{time.time() - t0:.0f}s")
        run = freya.get_iteration(sim, it)["runs"][0]
        report(run["callId"], v["customer_id"])
