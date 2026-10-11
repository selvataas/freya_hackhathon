"""Brief -> spec with Claude. Two extractions in parallel; if they differ, one reconciliation call."""
import concurrent.futures, hashlib, json, os, pathlib, re, time

from spec_schema import SCHEMA, SCHEMA_VERSION, SITUATIONS, NOTE_SITUATIONS, TOOL_ROLES, RESPONSE_ROLES, PHRASES, NAMED_DATES

MODEL = os.environ.get("LLM_MODEL") or os.environ.get("BUILDER_MODEL") or "claude-opus-5-5"
EFFORT = os.environ.get("BUILDER_EFFORT", "high")
PROMPT_VERSION = "7"
CACHE = pathlib.Path(__file__).resolve().parent.parent / "cache"

INSTRUCTIONS = f"""You read a bank's specification ("brief") for an outbound collections phone call, and the bank's tool API (OpenAPI).
You fill a fixed JSON spec. A deterministic program turns the spec into the phone agent, so every rule must land in the right field.

General rules
- Take every value from the brief or the tool API. Never invent a rule, a number, a date or a name that is not there.
- The brief may be raw material: mails, policy extracts, memos that change earlier text, code lists. When a later text changes an earlier one, the later one wins.
- When several briefs are given, the later brief builds on the earlier ones: everything of the earlier brief applies unless the later one replaces it.
- Enum values (tool fields, outcomes, reasons, queues, product types, hint values) must be copied exactly from the tool API.

Phrases
- Every phrase must have text. If the brief quotes the exact wording, copy it character for character and set verbatim=true.
  Otherwise write one short natural sentence that follows the brief's rules for that moment, and set verbatim=false.
- Write every phrase in the language of the call: the language the brief's customers speak (the field language, an ISO 639-1
  code such as en or tr). A quoted wording stays as the brief gives it.
- Placeholders in angle brackets (<address>, <product>, <amount>, <days>, <date>, <time>) are filled by the program. Use only the ones named for that phrase.
- "opening" must satisfy every rule for the first sentence, and must not mention the debt, the product or the reason for the call.
- "identity_question": if the brief quotes the question with call variables, write it with <address> in place of the person's name and set verbatim=true.
- "debt_intro" says who is calling and why, as the brief requires after verification. "debt_line" is one sentence per product with <product>, <amount> and <days>.
- "goodbye" thanks the customer and says goodbye.

Situations (the program's own words). Map the brief's outcome table onto them in "outcomes", one row each:
{json.dumps(SITUATIONS)}
- promise_recorded: at least one promise recorded. transfer_*: the call was handed over (restructuring request, human request, hardship support).
- refused: no promise because the customer refused or did not want to talk (after verification). id_failed / id_declined: identity check failed / customer declined.
- callback / no_callback / wrong_number / deceased / unclear: the customer was not reached.
- If the brief gives no outcome for a situation, still add the row with the closest outcome and reason from the table.

Dates the program can propose: {json.dumps(NAMED_DATES)}
- end_of_this_week = the last business day of the current week. "deadline" = the band's deadline.

Persuasion: "attempts" lists the persuasion attempts in order (n = 1, 2, ...). For each: which bands it applies to (empty = all),
the amount (full, floor, or full_or_floor_if_too_much when the attempt uses the floor after the customer said the full amount is too much)
and the date. A band's "attempts" is how many attempts that band allows.

Tool roles. In tool_fields give one row per (tool, role) with the request field name from the tool API:
{json.dumps(TOOL_ROLES)}
In response_fields give one row per (tool, role) with the response field name:
{json.dumps(RESPONSE_ROLES)}
(For get_account the roles product_id, type, past_due, days_late are fields of each product in the list.)

Multi product: note_reasons maps these situations to the reason values of the note tool: {json.dumps(NOTE_SITUATIONS)}.

custom_situations: a situation of the brief that none of the fields above handles (the customer says something that needs its own
words and its own ending, for example a reason to end the call with its own outcome). Give its triggers, the text to say, and how the call goes on.
Do not repeat situations the fields already cover (already paid, dispute, hardship, restructuring, a human, not talking, third party, wrong number, deceased).

unplaced_rules: only a rule that no field above holds, custom_situations included, quoted word for word. Check every field before adding a rule:
a rule that a field already expresses (attempts, dates, amounts, identity, confirmation, recording, notes, outcomes, phrases) must not be listed.
Most briefs leave this list short or empty.
"""


API_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages"


def _http_messages(body, timeout=900):
    """The Messages API with the standard library only, for a Python without the anthropic package."""
    import urllib.request, urllib.error
    key = os.environ.get("ANTHROPIC_API_KEY") or ""
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    data = json.dumps(body).encode()
    last = None
    for attempt in range(4):
        req = urllib.request.Request(API_URL, data=data, method="POST", headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = RuntimeError(f"Messages API {e.code}: {e.read().decode()[:500]}")
            if e.code not in (408, 409, 429, 500, 502, 503, 504, 529):
                raise last from None
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(5 * (attempt + 1))
    raise last


def _complete(system, messages, effort=None):
    """Returns (text, stop_reason, input_tokens, output_tokens). The SDK when it is installed, plain HTTP otherwise."""
    try:
        import anthropic
    except ImportError:
        anthropic = None
    if anthropic is not None and hasattr(anthropic, "Anthropic"):
        try:
            client = anthropic.Anthropic(max_retries=3)
            with client.messages.stream(model=MODEL, max_tokens=64000, system=system, output_config={"effort": effort or EFFORT},
                                        messages=messages) as stream:
                msg = stream.get_final_message()
            text = "".join(b.text for b in msg.content if b.type == "text")
            return text, msg.stop_reason, msg.usage.input_tokens, msg.usage.output_tokens
        except TypeError:
            pass  # an old SDK without output_config: use plain HTTP
    r = _http_messages({"model": MODEL, "max_tokens": 32000, "system": system, "output_config": {"effort": effort or EFFORT}, "messages": messages})
    text = "".join(b.get("text", "") for b in r.get("content") or [] if b.get("type") == "text")
    u = r.get("usage") or {}
    return text, r.get("stop_reason"), u.get("input_tokens"), u.get("output_tokens")


def validate(node, schema, path="spec"):
    """A small JSON-schema check for the subset SCHEMA uses. Returns a list of problems."""
    errs = []
    if "anyOf" in schema:
        if node is None:
            return errs
        return validate(node, schema["anyOf"][0], path)
    t = schema.get("type")
    if t == "object":
        if not isinstance(node, dict):
            return [f"{path}: expected an object"]
        for k in schema.get("required") or []:
            if k not in node:
                errs.append(f"{path}.{k}: missing")
        for k, v in node.items():
            if k in (schema.get("properties") or {}):
                errs += validate(v, schema["properties"][k], f"{path}.{k}")
            else:
                errs.append(f"{path}.{k}: not in the schema")
    elif t == "array":
        if not isinstance(node, list):
            return [f"{path}: expected an array"]
        for i, x in enumerate(node):
            errs += validate(x, schema.get("items") or {}, f"{path}[{i}]")
    elif t == "string":
        if not isinstance(node, str):
            errs.append(f"{path}: expected a string")
        elif schema.get("enum") and node not in schema["enum"]:
            errs.append(f"{path}: {node!r} is not one of {schema['enum']}")
    elif t == "integer":
        if not isinstance(node, int) or isinstance(node, bool):
            errs.append(f"{path}: expected an integer")
    elif t == "boolean":
        if not isinstance(node, bool):
            errs.append(f"{path}: expected true or false")
    return errs


def _json_from(text):
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        raise ValueError("no JSON object in the answer")
    return json.loads(text[a:b + 1])


def _ask(trace, purpose, system, messages):
    t0 = time.time()
    text, stop, tin, tout = _complete(system, messages)
    trace.event("model_call", model=MODEL, purpose=purpose, effort=EFFORT, stop_reason=stop,
                input_tokens=tin, output_tokens=tout, seconds=round(time.time() - t0, 1))
    if stop != "end_turn":
        raise RuntimeError(f"{purpose}: stop_reason {stop}")
    return text


def _call(trace, purpose, system, user):
    system = system + "\n\nAnswer with one JSON object that follows this JSON schema exactly, and nothing else:\n" + json.dumps(SCHEMA)
    messages = [{"role": "user", "content": user}]
    text = _ask(trace, purpose, system, messages)
    for attempt in range(2):
        try:
            spec = _json_from(text)
            errs = validate(spec, SCHEMA)
        except Exception as e:
            spec, errs = None, [f"the answer is not valid JSON: {e}"]
        if not errs:
            return spec
        trace.event("spec_invalid", purpose=purpose, problems=errs[:30])
        if attempt == 1:
            break
        messages = messages + [{"role": "assistant", "content": text},
                               {"role": "user", "content": "The JSON does not follow the schema:\n" + "\n".join(errs[:60]) + "\nAnswer with the corrected complete JSON object only."}]
        text = _ask(trace, purpose + " (repair)", system, messages)
    if spec is None:
        raise RuntimeError(f"{purpose}: no usable spec")
    return spec


def _user(briefs, openapi_text):
    parts = []
    for i, (name, text) in enumerate(briefs):
        parts.append(f"<brief index=\"{i + 1}\" file=\"{name}\">\n{text}\n</brief>")
    parts.append(f"<tool_api>\n{openapi_text}\n</tool_api>")
    parts.append("Fill the spec.")
    return "\n\n".join(parts)


def _canon(spec):
    """The parts that change the agent's behaviour. Wording of non-verbatim phrases and notes do not count."""
    s = json.loads(json.dumps(spec))
    for k, p in (s.get("phrases") or {}).items():
        if isinstance(p, dict) and not p.get("verbatim"):
            p["text"] = ""
    for r in s.get("unplaced_rules") or []:
        r["note"] = ""
    # free wording the runtime says as it is: a different wording is not a different rule
    for q in (s.get("identity") or {}).get("questions") or []:
        q["ask_text"] = ""
    for h in (s.get("identity") or {}).get("hints") or []:
        h["instruction"] = ""
    s.pop("forbidden", None)
    for key in ("hardship", "requests"):
        obj = s.get(key) or {}
        for v in [obj] + [x for x in obj.values() if isinstance(x, dict)]:
            if isinstance(v, dict):
                v.pop("trigger_examples", None)
    for k in ("tool_fields", "response_fields", "outcomes", "products", "bands", "tool_constants", "unplaced_rules"):
        if isinstance(s.get(k), list):
            s[k] = sorted(s[k], key=lambda x: json.dumps(x, sort_keys=True))
    s.pop("unplaced_rules", None)
    return s


def _diff(a, b, path=""):
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k), b.get(k), f"{path}.{k}" if path else k)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            out += _diff(x, y, f"{path}[{i}]")
    elif a != b:
        out.append(path)
    return out


def cache_key(briefs, openapi_text):
    h = hashlib.sha256()
    for name, text in briefs:
        h.update(text.encode())
    h.update(openapi_text.encode())
    h.update((SCHEMA_VERSION + PROMPT_VERSION + MODEL + EFFORT).encode())
    return h.hexdigest()[:16]


def extract(briefs, openapi_text, trace, use_cache=True, allow_llm=True):
    key = cache_key(briefs, openapi_text)
    path = CACHE / f"spec-{key}.json"
    if use_cache and path.exists():
        trace.event("spec_cache_hit", key=key)
        return json.loads(path.read_text()), {"cached": True, "key": key}
    if not allow_llm:
        raise SystemExit(f"--no-llm: no cached spec for this brief and model ({MODEL}), key {key}; nothing was called")
    user = _user(briefs, openapi_text)
    with concurrent.futures.ThreadPoolExecutor(2) as ex:
        futs = [ex.submit(_call, trace, f"extract spec from brief (run {i + 1} of 2)", INSTRUCTIONS, user) for i in range(2)]
        a, b = [f.result() for f in futs]
    diff = _diff(_canon(a), _canon(b))
    trace.event("spec_compare", differences=len(diff), paths=diff[:60])
    final = a
    if diff:
        rec = (user + "\n\nTwo earlier readings of these briefs disagree on these fields:\n" + "\n".join(diff[:80]) +
               "\n\n<reading_a>\n" + json.dumps(a) + "\n</reading_a>\n<reading_b>\n" + json.dumps(b) + "\n</reading_b>\n\n"
               "Read the briefs again for each disputed field and decide which reading is right (or neither). Output the final spec.")
        final = _call(trace, "reconcile two spec readings", INSTRUCTIONS, rec)
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps(final, indent=1))
    return final, {"cached": False, "key": key, "differences": diff}


def check_verbatim(spec, briefs, warn):
    """A phrase marked verbatim must appear in the brief (placeholders aside)."""
    norm = lambda s: re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()
    corpus = norm(" ".join(t for _, t in briefs))
    for k, p in (spec.get("phrases") or {}).items():
        if isinstance(p, dict) and p.get("verbatim"):
            pieces = [x for x in re.split(r"<[a-z_]+>|\{[a-z_]+\}", norm(p.get("text") or "")) if len(x.strip(" .,?!\"'")) > 3]
            missing = [x for x in pieces if x.strip(" .,?!\"'") not in corpus]
            if missing:
                warn(f"phrase {k} is marked verbatim but is not in the brief: {missing[:2]}")
