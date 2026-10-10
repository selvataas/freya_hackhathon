"""Turn a normalized spec and the tool API into a Freya workflow. Deterministic: same input, same JSON."""
import ast, json, pathlib

RUNTIME = (pathlib.Path(__file__).parent / "runtime.py").read_text()
EMPTY = "none"  # the value a consumed enum variable is reset to; the platform rejects "" for an enum
TALK_PHASES = ("talk_pre", "talk_id", "talk_main")
NUMERIC = ("number", "integer")


def _code_node(name, code, targets):
    return {"name": name, "node_type": "code", "passthrough": True, "passthrough_default_transition": "bye",
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                             "parameters": {"type": "object", "properties": {
                                 "code": {"type": "string", "default": code},
                                 "timeout_ms": {"type": "number", "default": 20000}}}}}],
            # a brain run that failed leaves next_step from the run before: never act on it (it could repeat a bank call)
            "transitions": [_gt(name + "_failure_count", 0, "bye")] + [_eq("next_step", t, t) for t in targets] + [_always("bye")]}


def _gt(var, n, target):
    # a loop guard on the engine's own failure counter: a step that keeps failing must not spin forever
    return {"target_node": target, "description": f"{var} above {n}",
            "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "greater_than", "operand": n}]}}


def _eq(var, val, target):
    return {"target_node": target, "description": f"{var} is {val}",
            "condition": {"logic": "or", "conditions": [{"variable": var, "operator": "equals", "operand": val}]}}


def _always(target):
    return {"target_node": target, "description": "always", "condition": {"operator": "always"}}


def _minify(src):
    """Drop comments and docstrings: a smaller snippet runs faster in the sandbox."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)) and node.body and isinstance(node.body[0], ast.Expr) \
                and isinstance(getattr(node.body[0], "value", None), ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:] or [ast.Pass()]
    out = []
    for line in ast.unparse(tree).splitlines():
        n = len(line) - len(line.lstrip(" "))
        out.append(" " * (n // 4) + line.lstrip(" "))
    return "\n".join(out)


RUNTIME_KEYS = ("variables", "phrases", "presence", "third_party", "identity", "calendar", "products", "bands", "promise_date",
                "amounts", "persuasion", "hardship", "requests", "promise", "outcomes", "multi_product", "tool_fields", "response_fields")


def runtime_spec(spec):
    """Only what the brain reads; prompts and extraction carry the rest."""
    s = dict((k, spec.get(k)) for k in RUNTIME_KEYS)
    s["phrases"] = dict((k, {"text": (v or {}).get("text") or ""}) for k, v in (spec.get("phrases") or {}).items())
    s["hardship"] = dict((k, v) for k, v in (spec.get("hardship") or {}).items() if k != "trigger_examples")
    s["requests"] = dict((k, dict((a, b) for a, b in (v or {}).items() if a != "trigger_examples")) for k, v in (spec.get("requests") or {}).items())
    return s


def _strings(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)


def _spec_literal(spec):
    # a Python literal is half the size of a hex string; closing braces are spaced so no double brace appears
    if any("{{" in t or "}}" in t or "{" + "}" in t for t in _strings(spec)):
        return "json.loads(bytes.fromhex('" + json.dumps(spec, sort_keys=True).encode().hex() + "').decode('utf-8'))"
    lit = repr(spec)
    while "}}" in lit or "{{" in lit:
        lit = lit.replace("}}", "} }").replace("{{", "{ {")
    return lit


def brain_code(spec):
    code = _minify(RUNTIME) + "\n_SPEC = " + _spec_literal(runtime_spec(spec)) + "\nbrain(vars, _SPEC)\n"
    if "{{" in code or "}}" in code:
        raise ValueError("runtime code contains a double curly brace; the platform would template it")
    return code


def _pre_hook(tool):
    # cast numbers, drop empty optional fields: values arrive as strings from the variable table
    numeric = [f for f, d in tool["fields"].items() if d["type"] in NUMERIC]
    return ("try:\n"
            "    b = config.get('body')\n"
            "    if isinstance(b, dict):\n"
            "        for k in list(b.keys()):\n"
            "            v = b.get(k)\n"
            "            if v is None or (isinstance(v, str) and (v.strip() == '' or v.strip().startswith('{' + '{'))):\n"
            "                b.pop(k, None)\n"
            f"        for k in {numeric!r}:\n"
            "            if k in b:\n"
            "                try:\n"
            "                    f = float(str(b[k]).replace(',', ''))\n"
            "                    b[k] = int(f) if f == int(f) and k in " + repr([f for f, d in tool["fields"].items() if d["type"] == "integer"]) + " else f\n"
            "                except Exception:\n"
            "                    pass\n"
            "except Exception:\n"
            "    pass\n")


def _post_hook(tool, ok_field):
    name = tool["name"]
    return ("try:\n"
            "    import json\n"
            "    if isinstance(result, dict):\n"
            "        result.pop('header', None)\n"
            "        d = result.get('data')\n"
            f"        good = isinstance(d, dict) and d.get({ok_field!r}, True) is not False and not d.get('error')\n"
            "        if isinstance(d, dict):\n"
            "            d['what_to_do_next'] = ('Done. Follow your current task.' if good else "
            "'FAILED: this was NOT carried out and nothing was recorded. Never tell the customer it was done. Follow your current task.')\n"
            "        try:\n"
            f"            vars['res_{name}'] = json.dumps(d) if isinstance(d, dict) else 'null'\n"
            "        except Exception:\n"
            "            pass\n"
            "except Exception:\n"
            "    pass\n")


def _api_tool(tool, spec, lifecycle=False):
    call_vars = set((spec.get("variables") or {}).get("all") or []) | {(spec.get("variables") or {}).get("customer_id") or "customer_id"}
    consts = dict((c["field"], c["value"]) for c in spec.get("tool_constants") or [] if c.get("tool") == tool["name"])
    props = {}
    for f, d in tool["fields"].items():
        leaf = {"type": d["type"] if d["type"] in ("string", "number", "integer", "boolean") else "string"}
        if d["enum"]:
            leaf["enum"] = d["enum"]
        if f in consts:
            leaf["default"] = consts[f]
        elif f in call_vars:
            leaf["default"] = "{{" + f + "}}"
        elif lifecycle:
            role = next((r["role"] for r in spec.get("tool_fields") or [] if r.get("tool") == tool["name"] and r.get("field") == f), f)
            leaf["default"] = "{{final_" + role + "}}"
        else:
            leaf["default"] = "{{a_" + tool["name"] + "_" + f + "}}"
        props[f] = leaf
    ok_field = next((r["field"] for r in spec.get("response_fields") or [] if r.get("tool") == tool["name"] and r.get("role") == "ok"), "ok")
    t = {"type": "function", "config": {"timeoutMs": 30000, "maxRetries": 0},
         "function": {"name": tool["name"], "handler": "__function__:api_call", "description": tool["summary"] or tool["name"],
                      "parameters": {"type": "object", "properties": {
                          "url": {"type": "string", "default": tool["url"]},
                          "method": {"type": "string", "default": tool["method"]},
                          "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}},
                          "body": {"type": "object", "properties": props, "required": []}}}},
         "post_process_code": _post_hook(tool, ok_field)}
    if lifecycle or any(d["type"] in NUMERIC for d in tool["fields"].values()):
        t["pre_process_code"] = _pre_hook(tool)  # only where needed: every hook is one more sandbox run
    if lifecycle:
        t["config"]["alwaysRunsAt"] = ["end_of_call"]
    return t


def _api_node(tool, spec, targets):
    """The tool's post-hook also runs the brain, so the next step is decided without another code-node run.
    The hook writes `route`; if it did not run, `route` is still 'brain' and the node falls back to the brain node."""
    t = _api_tool(tool, spec)
    # each tool node has its own route variable, written only by its own hook: a hook that did not run
    # (a timeout under load) leaves it at 'brain', never at a stale value from another node
    rv = "route_" + tool["name"]
    t["post_process_code"] = (t["post_process_code"] + "\n" + brain_code(spec) +
                              f"try:\n    vars['{rv}'] = vars.get('next_step') or 'brain'\nexcept Exception:\n    pass\n")
    return {"name": "do_" + tool["name"], "node_type": "api_request", "passthrough": True, "passthrough_default_transition": "brain",
            "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
            "pre_actions": [t], "response_mapping": [{"path": "data", "variable": "raw_" + tool["name"]}],
            "transitions": [_gt("do_" + tool["name"] + "_failure_count", 4, "bye")] + [_eq(rv, x, x) for x in targets] + [_always("brain")]}


def _ex(name, typ, desc, enum=None):
    # free text gets a low bar: a discarded value leaves no trace and looks like silence
    x = {"name": name, "type": typ, "description": desc, "min_confidence": 0.5, "max_retries": 0}
    if enum:
        x["enum_values"] = enum + ([EMPTY] if EMPTY not in enum else [])
    return x


def _examples(lst):
    lst = [str(x) for x in (lst or []) if x]
    return (" (for example: " + "; ".join(lst[:6]) + ")") if lst else ""


def _custom_field(spec, phase):
    want = ("before_verification", "any") if phase in ("talk_pre", "talk_id") else ("after_verification", "any")
    cs = [c for c in spec.get("custom_situations") or [] if c.get("applies_when") in want]
    if not cs:
        return []
    desc = "; ".join(c["name"] + " = " + "; ".join(str(x) for x in (c.get("trigger_examples") or [])[:5]) for c in cs)
    return [_ex("custom", "string", "Only if the LAST message is one of these situations: " + desc + ". Otherwise none.", [c["name"] for c in cs])]


def _state_field():
    return {"name": "message_state", "type": "string", "min_confidence": 0.5, "max_retries": 0, "enum_values": ["complete", "cut_off", "none"],
            "description": "cut_off = the LAST customer message stops in the middle: in the middle of a sentence, a word or a number, as if the customer "
                           "has not finished (for example it ends with 'and', 'to', 'the', 'my', a half word, or the first part of a number or a date). "
                           "complete = anything else, also a short answer like 'yes' or a number on its own."}


def extraction(spec, phase):
    return _extraction(spec, phase) + _custom_field(spec, phase) + [_state_field()]


def _extraction(spec, phase):
    hs, rq = spec.get("hardship") or {}, spec.get("requests") or {}
    q_kind = _ex("q_kind", "string", "Only if the customer's LAST message asks the agent a question: ai = asks if they talk to a robot, a machine or an AI; "
                 "scam = asks if this is a scam or fraud; purpose = asks what the call is about or who is calling; other = any other question; none = no question.",
                 ["ai", "scam", "purpose", "other"])
    if phase == "talk_pre":
        return [
            _ex("presence", "string", "Who is on the line, from the LAST message only. confirmed = the person says yes, that's me, speaking, or says the customer's own name as theirs; "
                "other_person = someone else answered (a relative, a colleague) or says the customer is not there; wrong_number = the number does not belong to the customer, they do not know the customer; "
                "deceased = says the customer has died; human = asks for a human or a real person; not_talking = says they do not want to talk; refuses = refuses to help; "
                "question = only asks a question; unclear = hello, go ahead, who is this, or anything else.",
                ["confirmed", "other_person", "wrong_number", "deceased", "human", "not_talking", "refuses", "question", "unclear"]),
            _ex("cb_phrase", "string", "If the LAST message says when the customer can be reached: the day and time words exactly as said, e.g. 'Thursday after two'. Empty otherwise."),
            q_kind]
    if phase == "talk_id":
        return [
            _ex("id_reply", "string", "What the LAST message does with the security question. answer = gives an answer (even partly or wrong); refuse = will not answer; "
                "asks_purpose = asks what the call is about instead of answering; human = asks for a human; not_talking = does not want to talk; question = asks another question; unclear = anything else.",
                ["answer", "refuse", "asks_purpose", "human", "not_talking", "question", "unclear"]),
            _ex("id_answer", "string", "The answer in the LAST message, exactly as said, words and digits as they are. If the customer corrects themselves, only the corrected value. Empty if none."),
            _ex("id_iso", "string", "Only if the LAST message gives a full date (day, month and year): that date as YYYY-MM-DD. Read a date given only as numbers as day, month, year. Empty otherwise."),
            q_kind]
    return [
        _ex("reply", "string", "What the LAST customer message does. yes = agrees to what the agent just asked or offered, or confirms; no = says no or cannot, without naming a day or an amount; "
            "propose = names a day or an amount themselves; too_much = says the amount is too much or too high; vague = names only a period or a condition, not a day; "
            "hardship = describes a serious personal hardship that makes paying hard, such as the brief names (being busy, tired or stressed is not hardship: that is other)" + _examples(hs.get("trigger_examples")) + "; "
            "already_paid = says they already paid" + _examples((rq.get("already_paid") or {}).get("trigger_examples")) + "; "
            "dispute = says the debt or the product is not theirs or never was theirs (refusing or being unwilling to pay is not a dispute: that is no)" + _examples((rq.get("dispute") or {}).get("trigger_examples")) + "; "
            "restructuring = asks to change the repayment terms" + _examples((rq.get("restructuring") or {}).get("trigger_examples")) + "; "
            "human = asks for a human or a real person; not_talking = does not want to talk; question = asks a question; "
            "change_recorded = wants to change or cancel a promise that was already recorded; other = anything else. "
            "When a message both refuses and names a day or amount, use propose. When it mentions hardship, use hardship.",
            ["yes", "no", "propose", "too_much", "vague", "hardship", "already_paid", "dispute", "restructuring", "human", "not_talking", "question", "change_recorded", "other"]),
        _ex("date_phrase", "string", "The words the customer used in the LAST message for the day they will PAY, exactly as said (e.g. 'Thursday', 'on the 3rd', 'the ninth of March'). "
            "If they correct themselves, only the corrected day. Not days that are about anything else. Empty if they named no payment day."),
        _ex("amount", "string", "The amount the customer offers to pay in the LAST message, in digits, e.g. 455.50. If they correct themselves, only the corrected amount. Empty if they named no amount."),
        _ex("applies_to_all", "string", "When the customer names a day or amount: yes = for all products / everything; no = only for one product; unknown = not said.", ["yes", "no", "unknown"]),
        q_kind]


def system_prompt(spec):
    f = spec.get("forbidden") or {}
    ph = spec.get("phrases") or {}
    lines = [
        f"You are the digital assistant of {spec.get('bank_name') or 'the bank'} on a phone call. Speak {spec.get('language') or 'en'}. One or two short sentences per turn.",
        "Your Current Task tells you what to say in this turn. Follow it exactly. Text in quotes is said word for word. Figures, dates and products come only from the Current Task: never invent or change them.",
        "You cannot call any tool. Never say that something is recorded, booked or done unless the Current Task says so.",
        "If the customer asks something the Current Task does not cover, say: \"" + ((ph.get("no_info") or {}).get("text") or "") + "\" and then do the Current Task.",
        "If the customer asks whether you are a robot or an AI, say: \"" + ((ph.get("ai_answer") or {}).get("text") or "") + "\"",
        "If the customer asks whether this is a scam, say: \"" + ((ph.get("scam_answer") or {}).get("text") or "") + "\"",
    ]
    if f.get("before_verification"):
        lines.append("Until the customer's identity is verified, never say: " + "; ".join(f["before_verification"]) + ". Say nothing about any account.")
    if f.get("offers"):
        lines.append("Never offer: " + "; ".join(f["offers"]) + ".")
    if f.get("questions"):
        lines.append("Never ask: " + "; ".join(f["questions"]) + ".")
    un = [r for r in spec.get("unplaced_rules") or [] if r.get("quote")]
    if un:
        lines.append("Also follow these rules of the bank, word for word:")
        lines += ["- " + r["quote"] for r in un]
    return "\n".join(lines)


TASK = ("{{instruction}}\n\n"
        "No tool call is allowed in this turn. Do not say goodbye unless the instruction says so.")


def _talk_nodes(spec):
    out = {}
    for phase in TALK_PHASES:
        ex = extraction(spec, phase)
        for kind in ("fixed", "llm"):
            name = f"{phase}_{kind}"
            out[name] = {"name": name, "node_type": "conversation",
                         "on_enter": {"type": "tts", "text": "{{say_line}}"} if kind == "fixed" else {"type": "llm"},
                         "task_message": TASK, "extraction_schema": ex, "tools": [],
                         "max_node_turns": 60, "max_turn_transition": "brain",
                         "transitions": [_always("brain")]}
    return out


def render(spec, tools):
    nodes = {}
    used = [t for t in ("verify_identity", "get_account", "create_promise", "add_note", "schedule_callback", "transfer_to_agent") if t in tools]
    targets = [f"{p}_{k}" for p in TALK_PHASES for k in ("fixed", "llm")] + ["do_" + t for t in used] + ["bye"]
    nodes["brain"] = _code_node("brain", brain_code(spec), targets)
    nodes.update(_talk_nodes(spec))
    for t in used:
        nodes["do_" + t] = _api_node(tools[t], spec, targets)
    nodes["bye"] = {"name": "bye", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                    "transitions": [],
                    "terminal": {"type": "function", "function": {"name": "call_closed", "handler": "__function__:end_call",
                                 "parameters": {"type": "object", "properties": {
                                     "message_mode": {"type": "string", "default": "custom"},
                                     "spoken_message": {"type": "string", "default": "{{farewell}}"}}}}}}
    wf = {"initial_node": "brain", "system_prompt": system_prompt(spec), "global_nodes": {}, "nodes": nodes,
          "test_variables": {(spec.get("variables") or {}).get("customer_id") or "customer_id": "c_test"},
          "tools": [_api_tool(tools["close_call"], spec, lifecycle=True)] if "close_call" in tools else []}
    return wf
