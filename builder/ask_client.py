"""Optional layer: ask the client about points the brief leaves unclear, and fold the answers into the spec.

Off by default. On with --ask-client or CLIENT_MODE=1. When off, the builder runs exactly as without this file:
the extraction prompt and the spec cache are not touched.

    spec -> questions (one model call) -> transport (who answers) -> changes (one model call) -> checked spec

The transport is replaceable. Today there is one: FileTransport, a local JSON file with fixed answers. When the
organisers publish how a simulated client is reached, a new transport with the same ask() method plugs in here.
The model calls are passed in as a function, so the layer can be tested without any API call.
"""
import copy, hashlib, json, os, pathlib, re, time

MAX_QUESTIONS = 5
EFFORT = os.environ.get("CLIENT_EFFORT", "low")
CACHE = pathlib.Path(__file__).resolve().parent.parent / "cache"
DEFAULT_ANSWER = "No further information. Follow the brief as written."

QUESTIONS_SYSTEM = f"""You review a JSON spec that was read from a bank's brief for an outbound collections phone call.
List the points where the brief is genuinely unclear or contradictory, so that the spec had to guess, and where a wrong
guess would change what the phone agent does or records. Ask the bank's client about them.

- At most {MAX_QUESTIONS} questions, the most important first. Fewer is better; none is fine.
- Each question is one short sentence a bank employee can answer without reading the spec.
- Do not ask about anything the brief states clearly. Do not ask about wording.
- "about" is the spec path the answer would change, e.g. bands[0].deadline_n or third_party.window_end.

Answer with one JSON object and nothing else: {{"questions": [{{"id": "q1", "question": "...", "about": "..."}}]}}"""

CHANGES_SYSTEM = """You update a JSON spec of a bank's collections phone agent with the client's answers to questions about
the brief. Change only what an answer clearly settles. An answer that gives no new information changes nothing.

Answer with one JSON object and nothing else:
{"changes": [{"path": "bands[0].deadline_n", "value": 7, "because": "q1"}]}
A path uses dots for keys and [n] for list items, and must already exist in the spec. The value has the same type as the
value it replaces."""


def enabled(flag=False):
    return bool(flag) or os.environ.get("CLIENT_MODE", "").strip().lower() in ("1", "true", "yes", "on", "file")


class FileTransport:
    """Fixed answers from a local JSON file: {"answers": {"<id or question>": "<answer>"}, "default": "<answer>"}."""

    def __init__(self, path):
        self.path = str(path)
        data = json.load(open(path)) if path and os.path.exists(path) else {}
        self.answers = data.get("answers") or {}
        self.default = data.get("default") or DEFAULT_ANSWER

    def ask(self, question):
        a = self.answers.get(question.get("id")) or self.answers.get(question.get("question"))
        if a is None:
            # a key may also be a few words that the question contains
            for k, v in self.answers.items():
                if len(k) > 8 and k.lower() in (question.get("question") or "").lower():
                    a = v
                    break
        return a if a is not None else self.default

    def fingerprint(self):
        return hashlib.sha256(json.dumps({"a": self.answers, "d": self.default}, sort_keys=True).encode()).hexdigest()[:12]


def model_llm(trace):
    """The real model call, through the extraction module's client (SDK or plain HTTP)."""
    import extract

    def call(purpose, system, user):
        t0 = time.time()
        text, stop, tin, tout = extract._complete(system, [{"role": "user", "content": user}], effort=EFFORT)
        trace.event("model_call", model=extract.MODEL, purpose=purpose, effort=EFFORT, stop_reason=stop,
                    input_tokens=tin, output_tokens=tout, seconds=round(time.time() - t0, 1))
        if stop != "end_turn":
            raise RuntimeError(f"{purpose}: stop_reason {stop}")
        return extract._json_from(text)
    return call


def _get(spec, path):
    cur = spec
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path):
        if part.startswith("["):
            cur = cur[int(part[1:-1])]
        else:
            cur = cur[part]
    return cur


def _set(spec, path, value):
    parts = re.findall(r"[^.\[\]]+|\[\d+\]", path)
    cur = spec
    for part in parts[:-1]:
        cur = cur[int(part[1:-1])] if part.startswith("[") else cur[part]
    last = parts[-1]
    if last.startswith("["):
        cur[int(last[1:-1])] = value
    else:
        if last not in cur:
            raise KeyError(path)
        cur[last] = value


def apply_changes(spec, changes, schema, validate, trace):
    """Each change is applied on its own and kept only if the spec still follows the schema."""
    s = copy.deepcopy(spec)
    for c in changes or []:
        path, value = c.get("path") or "", c.get("value")
        try:
            old = _get(s, path)
        except Exception:
            trace.event("client_change_rejected", path=path, value=value, why="no such path in the spec")
            continue
        trial = copy.deepcopy(s)
        try:
            _set(trial, path, value)
        except Exception as e:
            trace.event("client_change_rejected", path=path, value=value, why=repr(e))
            continue
        errs = validate(trial, schema)
        if errs:
            trace.event("client_change_rejected", path=path, value=value, why="; ".join(errs[:3]))
            continue
        s = trial
        trace.event("client_change", path=path, old=old, new=value, because=c.get("because"))
    return s


def run(spec, briefs, transport, trace, llm=None, allow_llm=True, use_cache=True):
    """Returns the spec with the client's answers folded in. Never raises: on any failure the spec comes back unchanged."""
    import extract
    from spec_schema import SCHEMA
    key = hashlib.sha256((json.dumps(spec, sort_keys=True) + transport.fingerprint() + extract.MODEL + EFFORT).encode()).hexdigest()[:16]
    path = CACHE / f"client-{key}.json"
    trace.event("client_start", transport=type(transport).__name__, source=getattr(transport, "path", ""), key=key)
    if use_cache and path.exists():
        cached = json.loads(path.read_text())
        for qa in cached["qa"]:
            trace.event("client_qa", **qa)
        trace.event("client_cache_hit", key=key, changes=len(cached.get("changes") or []))
        return apply_changes(spec, cached.get("changes"), SCHEMA, extract.validate, trace)
    if llm is None:
        if not allow_llm:
            trace.event("warning", message="ask-client: not cached and no model call allowed; the spec is used as it is")
            return spec
        llm = model_llm(trace)
    text = "\n\n".join(f'<brief file="{n}">\n{t}\n</brief>' for n, t in briefs)
    try:
        qs = (llm("list unclear points of the brief as questions for the client", QUESTIONS_SYSTEM,
                  text + "\n\n<spec>\n" + json.dumps(spec) + "\n</spec>") or {}).get("questions") or []
    except Exception as e:
        trace.event("warning", message=f"ask-client: questions failed: {e!r}"[:300])
        return spec
    qa = []
    for q in qs[:MAX_QUESTIONS]:
        if not isinstance(q, dict) or not q.get("question"):
            continue
        q.setdefault("id", f"q{len(qa) + 1}")
        answer = transport.ask(q)
        item = {"id": q["id"], "question": q["question"], "about": q.get("about") or "", "answer": answer}
        qa.append(item)
        trace.event("client_qa", **item)
    changes = []
    informative = [x for x in qa if x["answer"] and x["answer"] != transport.default]
    if informative:
        try:
            changes = (llm("fold the client's answers into the spec", CHANGES_SYSTEM,
                           text + "\n\n<spec>\n" + json.dumps(spec) + "\n</spec>\n\n<answers>\n" + json.dumps(informative) + "\n</answers>") or {}).get("changes") or []
        except Exception as e:
            trace.event("warning", message=f"ask-client: changes failed: {e!r}"[:300])
            changes = []
    CACHE.mkdir(exist_ok=True)
    path.write_text(json.dumps({"qa": qa, "changes": changes}, indent=1))
    return apply_changes(spec, changes, SCHEMA, extract.validate, trace)
