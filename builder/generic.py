"""The builder's generic path: for a call the collections template does not fit (its tool API lacks the template's
tools). The model reads the documents into a small generic spec: the call's language and variables, the opening and
closing lines, the agent's instructions and, for every operation of the tool API, when to call it and which request
fields come from call variables. The workflow is rendered from that spec deterministically: a code step that writes a
calendar from the call's date (so that no date is left to the model's arithmetic), then one dialogue step that holds the
API's operations as tools. Nothing here knows a brief.
"""
import hashlib, json, pathlib, re, time

CACHE = pathlib.Path(__file__).resolve().parent.parent / "cache"
GENERIC_VERSION = "3"
TEMPLATE_TOOLS = {"verify_identity", "get_account", "create_promise", "close_call"}


def fits_template(tools):
    """The collections template needs its own tools in the API."""
    return TEMPLATE_TOOLS <= set(tools)


SCHEMA = {
    "type": "object",
    "required": ["language", "business_name", "variables", "date_variable", "opening", "instructions", "tools", "closing_line", "goodbye_words"],
    "properties": {
        "language": {"type": "string", "description": "The language of the call as an ISO 639-1 code (en, tr, ...)."},
        "business_name": {"type": "string"},
        "variables": {"type": "array", "description": "Every variable the call starts with, as the documents name it.",
                      "items": {"type": "object", "required": ["name", "meaning", "example"],
                                "properties": {"name": {"type": "string"}, "meaning": {"type": "string"}, "example": {"type": "string"}}}},
        "date_variable": {"type": "string", "description": "The variable that holds the call's date and time, or empty."},
        "opening": {"type": "string", "description": "The agent's first sentence, in the call's language. Call variables as {{name}}."},
        "instructions": {"type": "string", "description": "Everything the agent must do and know, for the agent ('you'): the goal; the steps "
                         "in order; every rule, limit, date and amount rule, with the later document winning where documents disagree; "
                         "what to say in each situation (customer-facing sentences in the call's language, in quotes); when to call which "
                         "tool and how to read its answer, including errors; what the agent must never do or say; how the call ends."},
        "tools": {"type": "array", "description": "One entry for every operation of the tool API.",
                  "items": {"type": "object", "required": ["name", "when", "fields_from_variables"],
                            "properties": {"name": {"type": "string", "description": "The operation's name exactly as the tool API gives it."},
                                           "when": {"type": "string", "description": "Imperative: 'Call this to ... when ...', and what to do with its answer."},
                                           "fields_from_variables": {"type": "array", "items": {"type": "object", "required": ["field", "variable"],
                                                                     "properties": {"field": {"type": "string"}, "variable": {"type": "string"}}}}}}},
        "start_tools": {"type": "array", "items": {"type": "string"},
                        "description": "Read-only lookups whose inputs all come from the call's variables and that the agent needs before "
                                       "anything else; the program runs them before the conversation starts. Never an operation that changes anything."},
        "closing_line": {"type": "string", "description": "The sentence the program says to end the call when the customer has nothing else, in the call's language."},
        "end_lines": {"type": "array", "items": {"type": "string"},
                      "description": "Every sentence after which the call is over (the closing, every hand-over, ending on silence), word for word in the call's language."},
        "goodbye_words": {"type": "array", "items": {"type": "string"}, "description": "Short words or phrases that close a call in the call's language."},
    },
}

INSTRUCTIONS = """You read a business's documents about one kind of phone call and its tool API (OpenAPI), and fill a JSON spec for
the phone agent. A program builds the agent from the spec: one dialogue step that holds the API's operations as tools,
and a calendar of the coming days written from the call's date.

- Take every rule, value, sentence and name from the documents and the tool API; invent nothing. Where documents
  disagree, the later one wins (by its date, or by its place when it has none: announcements and answers to questions
  come last).
- "instructions" is the dialogue model's whole briefing: complete and concrete, in English, with the sentences the agent
  says to the customer in the call's language, in quotes. The agent can only call the tools; tell it which tool gives
  which fact, never to state a fact a tool has not given, never to say an action was done unless the tool's answer says
  so, and what to say when a tool fails. It must use the calendar it is given for every day and date.
- "tools": every operation of the tool API, with its exact name. "when" is what the model reads to decide to call it.
  "fields_from_variables" lists request fields that the program fills from a call variable (for example an id the call
  starts with); every other field the agent fills from the conversation.
- "start_tools": the lookups the agent always needs first, when their inputs are all call variables (for example
  reading the caller's records by an id the call starts with). Their answers are in the agent's briefing from the
  first turn. Never list an operation that changes anything.
- "end_lines": every sentence after which the call is over, word for word. The call ends when the agent says one of
  them; the instructions say when to say which. When the customer simply has nothing else, the program says
  "closing_line" and ends the call.
- Every text the agent says is said to the customer, in the second person, never an instruction to the agent."""


def cache_key(briefs, api_text, model, effort):
    h = hashlib.sha256()
    for _, t in briefs:
        h.update(t.encode())
    h.update(api_text.encode())
    h.update((GENERIC_VERSION + json.dumps(SCHEMA, sort_keys=True) + INSTRUCTIONS + model + effort).encode())
    return h.hexdigest()[:16]


def _problems(spec, tools):
    out = []
    for k in SCHEMA["required"]:
        if k not in spec:
            out.append(f"missing {k}")
    names = [t.get("name") for t in spec.get("tools") or [] if isinstance(t, dict)]
    for n in tools:
        if n not in names:
            out.append(f"no entry for the tool {n}")
    for n in names:
        if n not in tools:
            out.append(f"{n} is not a tool of the API")
    return out


def extract(briefs, api_text, tools, trace, use_cache=True, allow_llm=True):
    import extract as ex
    key = cache_key(briefs, api_text, ex.MODEL, ex.EFFORT)
    path = CACHE / f"generic-{key}.json"
    if use_cache and path.exists():
        trace.event("spec_cache_hit", key=key, mode="generic")
        return json.loads(path.read_text()), {"cached": True, "key": key, "mode": "generic"}
    if not allow_llm:
        raise SystemExit(f"--no-llm: no cached generic spec for these documents (key {key}); nothing was called")
    system = INSTRUCTIONS + "\n\nAnswer with one JSON object that follows this JSON schema exactly, and nothing else:\n" + json.dumps(SCHEMA)
    user = ex._user(briefs, api_text).replace("Fill the spec.", "Fill the spec for this call.")
    messages = [{"role": "user", "content": user}]
    text = ex._ask(trace, "write the generic agent spec from the documents", system, messages)
    for attempt in range(2):
        try:
            spec = ex._json_from(text)
            probs = _problems(spec, tools)
        except Exception as e:
            spec, probs = None, [f"the answer is not valid JSON: {e}"]
        if not probs:
            break
        trace.event("spec_invalid", purpose="generic spec", problems=probs[:30])
        if attempt == 1:
            raise RuntimeError("generic spec: " + "; ".join(probs[:5]))
        messages = messages + [{"role": "assistant", "content": text},
                               {"role": "user", "content": "Fix these problems and answer with the complete JSON object only:\n" + "\n".join(probs)}]
        text = ex._ask(trace, "write the generic agent spec (repair)", system, messages)
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(spec, indent=1, ensure_ascii=False))
    return spec, {"cached": False, "key": key, "mode": "generic"}


# ---------------------------------------------------------------- render

WEEKDAYS = {"en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "tr": ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]}

# the calendar step: no curly braces next to each other, only json/re/datetime (the platform's rules for code)
CALENDAR_CODE = '''import re, datetime
names = NAMES
src = str(vars.get(DATEVAR) or "")
m = re.match(r"(\\d{4})-(\\d{2})-(\\d{2})", src)
try:
    today = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
except Exception:
    today = None
if today is None:
    vars["calendar"] = "unknown: ask the customer for the date"
else:
    lines = []
    monday = today - datetime.timedelta(days=today.weekday())
    for i in range(-7, 29):
        d = today + datetime.timedelta(days=i)
        week = (d - monday).days // 7
        tag = " (today)" if i == 0 else (" (tomorrow)" if i == 1 else (" (yesterday)" if i == -1 else ""))
        lines.append(d.isoformat() + " " + names[d.weekday()] + tag + ", " + ("this week" if week == 0 else ("next week" if week == 1 else ("last week" if week == -1 else str(week) + " weeks from this week"))))
    vars["calendar"] = "\\n".join(lines)
'''


# after the start lookups: their answers as one line per record, so that the dialogue model does not mix up records
FACTS_CODE = '''import json
def flat(x, prefix):
    lines = []
    if isinstance(x, dict):
        simple = [(k, v) for k, v in x.items() if not isinstance(v, (dict, list))]
        if simple:
            lines.append(prefix + "; ".join(str(k) + ": " + str(v) for k, v in simple))
        for k, v in x.items():
            if isinstance(v, (dict, list)):
                lines += flat(v, prefix + str(k) + " > ")
    elif isinstance(x, list):
        if not x:
            lines.append(prefix + "(none)")
        for i, v in enumerate(x):
            lines += flat(v, prefix + "#" + str(i + 1) + " ")
    else:
        lines.append(prefix + str(x))
    return lines
def natural(k):
    return [int(p) if p.isdigit() else p for p in k.split(".")]
for name in NAMES:
    raw = vars.get("start_" + name)
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        data = raw
    if data not in (None, "") and not isinstance(data, str):
        text = "\\n".join(flat(data, ""))
    else:
        # the engine also writes every result into the variable table flattened with dots: read it from there
        text = ""
        for pre in ("start_" + name + "_response.data.", name + "_response.data."):
            keys = sorted([k for k in vars.keys() if isinstance(k, str) and k.startswith(pre)], key=natural)
            if keys:
                text = "\\n".join(k[len(pre):] + ": " + str(vars.get(k)) for k in keys)
                break
        if not text and isinstance(data, str) and data:
            text = data
    vars["start_" + name + "_text"] = text or "no answer: call the tool yourself"
'''


def _leaf(d, default):
    leaf = {"type": d["type"] if d["type"] in ("string", "number", "integer", "boolean") else "string", "default": default}
    if d.get("enum"):
        leaf["enum"] = d["enum"]
    if d.get("description"):
        leaf["description"] = d["description"]
    return leaf


def _tool(t, entry, call_vars):
    mapped = dict((m["field"], m["variable"]) for m in entry.get("fields_from_variables") or [] if m.get("field") and m.get("variable"))
    props = {}
    for f, d in t["fields"].items():
        var = mapped.get(f) or (f if f in call_vars else None)
        props[f] = _leaf(d, "{{" + (var or f) + "}}")
    url = t["url"]
    for p in t.get("params") or []:
        var = mapped.get(p["name"]) or (p["name"] if p["name"] in call_vars else p["name"])
        if p["in"] == "path":
            url = url.replace("{" + p["name"] + "}", "{{" + var + "}}")
        elif p["in"] == "query":
            url += ("&" if "?" in url else "?") + p["name"] + "={{" + var + "}}"
    params = {"url": {"type": "string", "default": url}, "method": {"type": "string", "default": t["method"]},
              "headers": {"type": "object", "properties": {"Content-Type": {"type": "string", "default": "application/json"}}}}
    if t["method"] != "GET":
        params["body"] = {"type": "object", "properties": props, "required": [f for f, d in t["fields"].items() if d.get("required")]}
    when = (entry.get("when") or t.get("summary") or t["name"]).strip()
    return {"type": "function", "config": {"timeoutMs": 20000, "maxRetries": 1},
            "function": {"name": t["name"], "handler": "__function__:api_call",
                         "description": when + " Call one tool per message, and speak to the customer after every tool answer.",
                         "parameters": {"type": "object", "properties": params}}}


def _all_from_variables(t, entry, call_vars):
    """Every input of the operation comes from a call variable: the program can run it before the conversation."""
    mapped = dict((m["field"], m["variable"]) for m in entry.get("fields_from_variables") or [] if m.get("field") and m.get("variable"))
    names = [f for f, d in t["fields"].items() if d.get("required")] + [p["name"] for p in t.get("params") or [] if p.get("required") or p["in"] == "path"]
    return all((mapped.get(n) or (n if n in call_vars else None)) in call_vars for n in names)


def _end_call(spec):
    closing = (spec.get("closing_line") or "").strip()
    lines = [x.strip() for x in (spec.get("end_lines") or []) + [closing] if isinstance(x, str) and x.strip()]
    core = "|".join(re.escape(x.rstrip(".!?")) for x in dict.fromkeys(lines)) or "goodbye"
    words = "|".join(re.escape(w.strip()) for w in spec.get("goodbye_words") or [] if w.strip()) or "goodbye|bye"
    return {"type": "function", "config": {"timeoutMs": 10000},
            "function": {"name": "end_call", "handler": "__function__:end_call",
                         "parameters": {"type": "object", "properties": {
                             "message_mode": {"type": "string", "default": "none"}, "interruptible": {"type": "boolean", "default": True},
                             "trigger_pattern": {"type": "string", "default": core}, "trigger_timeout": {"type": "number", "default": 3},
                             "trigger_pattern_both": {"type": "string", "default": words}}},
                         "description": "Ends the call. You normally do NOT call this: an ending sentence ends the call by itself. "
                                        "Call it without any text only if the customer speaks after your closing sentence."}}


def render(spec, tools):
    lang = str(spec.get("language") or "en").lower()[:2]
    names = WEEKDAYS.get(lang, WEEKDAYS["en"])
    variables = [v for v in spec.get("variables") or [] if isinstance(v, dict) and v.get("name")]
    call_vars = set(v["name"] for v in variables)
    datevar = spec.get("date_variable") or ("now" if "now" in call_vars else "")
    entries = dict((e.get("name"), e) for e in spec.get("tools") or [] if isinstance(e, dict))
    api_tools = [_tool(tools[n], entries.get(n) or {}, call_vars) for n in sorted(tools)]
    var_lines = "\n".join(f"- {v['name']}: {v.get('meaning') or ''} (this call: {{{{{v['name']}}}}})" for v in variables)
    closing = (spec.get("closing_line") or "").strip()
    task = (spec.get("instructions") or "").strip() + "\n\n" + \
        "The call's variables:\n" + var_lines + "\n\n" + \
        "Calendar of the days around the call (use it for every day and date; never work a date out yourself):\n{{calendar}}\n" + \
        "Unless the instructions say otherwise, a weekday the customer names without more is its first day after today in the " \
        "calendar. Say a date to the customer as day, month and weekday in the call's language, never as YYYY-MM-DD; send dates to " \
        "tools as YYYY-MM-DD. Read times, amounts and names exactly as the tools give them.\n\n" + \
        "Answer what the customer asks with the facts you have before you go on with the steps. " \
        "Call one tool per message and speak to the customer after every tool answer. Never say that something was done unless " \
        "the tool's answer says so; when a tool fails, say so plainly."
    system = (f"You are the phone assistant of {spec.get('business_name') or 'the business'}. Speak only {lang}: "
              "one or two short sentences per turn, one question at a time. Follow the task of the current step.")
    opening = (spec.get("opening") or "").strip()
    cal = CALENDAR_CODE.replace("NAMES", json.dumps(names, ensure_ascii=False)).replace("DATEVAR", json.dumps(datevar or "now"))
    import render as R
    starts = [n for n in spec.get("start_tools") or [] if n in tools and _all_from_variables(tools[n], entries.get(n) or {}, call_vars)]
    if starts:
        task += "\n\nLooked up for you when the call started (use these answers; call the tool again only when you need something new):\n" + \
            "\n".join(f"- {n}, one line per record:\n{{{{start_{n}_text}}}}" for n in starts)
    ends = [x.strip() for x in spec.get("end_lines") or [] if isinstance(x, str) and x.strip()]
    task += ("\n\nThe call ends when you say one of these sentences, word for word; say nothing after it:\n" + "\n".join(f'- "{x}"' for x in ends)
             if ends else "") + \
        (f"\nWhen the customer simply has nothing else, the program says \"{closing}\" and ends the call." if closing else "")
    done = R._ex("done", "string", "yes = the customer's LAST message says they need nothing else, says goodbye or thanks to close the call, "
                 "or refuses to go on; no = anything else.", ["yes", "no"])
    main = {"name": "main", "node_type": "conversation", "position": {"x": 300, "y": 0},
            "on_enter": {"type": "tts", "text": opening} if opening else {"type": "llm"}, "on_enter_first_entry_only": True,
            "role_message": "", "task_message": task, "tools": api_tools + [_end_call(spec)], "transitions": [R._eq("done", "yes", "bye")],
            "assertions": [], "passthrough": False, "pre_actions": [], "interruptible": True, "max_node_turns": 80,
            "response_mapping": [], "extraction_schema": [done], "max_turn_transition": None, "truncation_strategy": "keep_all",
            "suppress_tool_results": False, "truncation_window_size": 10, "disable_inactivity_monitor": False,
            "passthrough_default_transition": None, "return_to_previous_on_interrupt": False}
    calendar = {"name": "calendar", "node_type": "code", "position": {"x": 0, "y": 0}, "passthrough": True,
                "passthrough_default_transition": "main", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                 "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": cal},
                                                                                "timeout_ms": {"type": "number", "default": 20000}}}}}],
                "transitions": [{"target_node": "main", "description": "always", "condition": {"operator": "always"}}]}
    if "{{" in cal.replace("{{calendar}}", "") or "}}" in cal:
        raise ValueError("calendar code contains a double curly brace")
    nodes = {"calendar": calendar}
    chain = ["start_" + n for n in starts] + (["facts"] if starts else []) + ["main"]
    calendar["passthrough_default_transition"] = chain[0]
    calendar["transitions"] = [{"target_node": chain[0], "description": "always", "condition": {"operator": "always"}}]
    for i, n in enumerate(starts):
        t = _tool(tools[n], entries.get(n) or {}, call_vars)
        t.pop("config", None)
        nodes["start_" + n] = {"name": "start_" + n, "node_type": "api_request", "position": {"x": 100 + 50 * i, "y": 100}, "passthrough": True,
                               "passthrough_default_transition": chain[i + 1], "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                               "pre_actions": [t], "response_mapping": [{"path": "data", "variable": "start_" + n}],
                               "transitions": [{"target_node": chain[i + 1], "description": "always", "condition": {"operator": "always"}}]}
    if starts:
        code = FACTS_CODE.replace("NAMES", json.dumps(starts))
        nodes["facts"] = {"name": "facts", "node_type": "code", "position": {"x": 200, "y": 0}, "passthrough": True,
                          "passthrough_default_transition": "main", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True,
                          "pre_actions": [{"type": "function", "function": {"name": "code_exec", "handler": "__function__:code_exec",
                                           "parameters": {"type": "object", "properties": {"code": {"type": "string", "default": code},
                                                                                          "timeout_ms": {"type": "number", "default": 20000}}}}}],
                          "transitions": [{"target_node": "main", "description": "always", "condition": {"operator": "always"}}]}
        if "{{" in code or "}}" in code:
            raise ValueError("facts code contains a double curly brace")
    nodes["main"] = main
    nodes["bye"] = {"name": "bye", "node_type": "end_call", "on_enter": {"type": "silent"}, "disable_inactivity_monitor": True, "transitions": [],
                    "terminal": {"type": "function", "function": {"name": "call_closed", "handler": "__function__:end_call",
                                 "parameters": {"type": "object", "properties": {"message_mode": {"type": "string", "default": "custom"},
                                                                                "spoken_message": {"type": "string", "default": closing or "."}}}}}}
    return {"nodes": nodes, "tools": [], "global_nodes": {}, "initial_node": "calendar",
            "system_prompt": system, "test_variables": dict((v["name"], v.get("example") or "") for v in variables)}


def check(spec, tools, wf):
    """The generic path's self-test: the parts the agent cannot do without. Returns [{name, pass, problems}]."""
    out = []
    def c(name, problems):
        out.append({"name": name, "pass": not problems, "problems": problems})
    main = wf["nodes"]["main"]
    names = [t["function"]["name"] for t in main["tools"]]
    c("every operation of the tool API is a tool of the agent", [n for n in tools if n not in names])
    c("every operation of the tool API has an entry in the spec", [n for n in tools if n not in [e.get("name") for e in spec.get("tools") or []]])
    c("every tool says when to call it", [e.get("name") for e in spec.get("tools") or [] if len((e.get("when") or "").strip()) < 15])
    c("the instructions name every tool", [n for n in tools if n not in (spec.get("instructions") or "")])
    call_vars = set(v.get("name") for v in spec.get("variables") or [])
    c("fields from variables name real variables", [f"{e.get('name')}.{m.get('field')} <- {m.get('variable')}" for e in spec.get("tools") or []
                                                    for m in e.get("fields_from_variables") or [] if m.get("variable") not in call_vars])
    c("fields from variables name real request fields", [f"{e.get('name')}.{m.get('field')}" for e in spec.get("tools") or [] if e.get("name") in tools
                                                         for m in e.get("fields_from_variables") or []
                                                         if m.get("field") not in tools[e["name"]]["fields"] and
                                                         m.get("field") not in [p["name"] for p in tools[e["name"]].get("params") or []]])
    c("an opening, a closing line and goodbye words", [k for k in ("opening", "closing_line") if not (spec.get(k) or "").strip()] +
      (["goodbye_words"] if not spec.get("goodbye_words") else []))
    c("start lookups are operations whose inputs all come from call variables",
      [n for n in spec.get("start_tools") or [] if n not in wf["nodes"].get("start_" + n, {}).get("name", "") ])
    c("the date variable is a call variable", [] if not spec.get("date_variable") or spec["date_variable"] in call_vars else [spec["date_variable"]])
    unresolved = [v for v in re.findall(r"\{\{([A-Za-z_][A-Za-z0-9_.]*)\}\}", main["on_enter"].get("text") or "") if v not in call_vars]
    c("the opening uses only call variables", unresolved)
    return out
