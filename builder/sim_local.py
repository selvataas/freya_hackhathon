"""Run the brain against scripted customers and a fake bank, without the platform. A development check.

    python3 builder/sim_local.py out/brief-a.spec.json [case_id ...] [-v] [--cases tests/variants/cases.json]

Each script turn is what the extraction model would produce for one customer message.
The fake bank names its fields as the spec maps them, so a brief whose tool API renames fields works too.
A case file holds cases in the public-test-set form plus a "script" list; their products carry their own ids.
"""
import copy, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runtime

try:
    CASES = {c["id"]: c for c in json.load(open(HERE.parent / "public-test-set.json"))}
except Exception:
    CASES = {}

SCRIPTS = {
    "PUB-01": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "14 March 1988"}, {"id_reply": "answer", "id_answer": "4471"},
               {"reply": "yes"}, {"reply": "yes"}],
    "PUB-02": [{"presence": "other_person", "q_kind": "purpose"}, {"presence": "other_person", "cb_phrase": "tomorrow morning around eleven"}],
    "PUB-03": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "12 July 1991"}, {"id_reply": "answer", "id_answer": "21 August 1992"},
               {"id_reply": "answer", "id_answer": "21 July 1990"}],
    "PUB-04": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "30 January 1984"}, {"id_reply": "answer", "id_answer": "2219"},
               {"reply": "propose", "date_phrase": "6 November"}, {"reply": "question", "q_kind": "ai"}, {"reply": "yes"}, {"reply": "yes"}],
    "PUB-05": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "9 September 1990"}, {"id_reply": "answer", "id_answer": "8846"},
               {"reply": "hardship"}, {"reply": "no"}],
    "PUB-06": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "17 May 1986"}, {"id_reply": "answer", "id_answer": "1502"},
               {"reply": "too_much"}, {"reply": "propose", "date_phrase": "this Friday"}, {"reply": "yes"}],
    "PUB-07": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "5 December 1975"}, {"id_reply": "answer", "id_answer": "7093"},
               {"reply": "vague", "date_phrase": "the week after next"}, {"reply": "propose", "date_phrase": "Monday the 26th"}, {"reply": "yes"}, {"reply": "yes"}],
    "PUB-08": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "28 April 1993"}, {"id_reply": "answer", "id_answer": "3317"},
               {"reply": "already_paid"}],
    "PUB-09": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "11 August 1981"}, {"id_reply": "answer", "id_answer": "5560"},
               {"reply": "restructuring"}],
    "PUB-10": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "23 February 1989"}, {"id_reply": "answer", "id_answer": "9904"},
               {"reply": "no"}, {"reply": "yes"}, {"reply": "yes"}],
    "PUB-11": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "3 June 1987"}, {"id_reply": "answer", "id_answer": "2288"},
               {"reply": "propose", "date_phrase": "this Friday", "applies_to_all": "yes"}, {"reply": "yes"}],
    "PUB-12": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "19 October 1983"}, {"id_reply": "answer", "id_answer": "4401"},
               {"id_reply": "answer", "id_answer": "4410"}, {"reply": "propose", "date_phrase": "tomorrow", "applies_to_all": "no"},
               {"reply": "no"}, {"reply": "no"}, {"reply": "no"}, {"reply": "yes"}],
    "PUB-13": [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "8 January 1991"}, {"id_reply": "answer", "id_answer": "6604"},
               {"reply": "propose", "date_phrase": "30 October", "applies_to_all": "yes"}, {"reply": "yes"}],
}


# variants of the public cases: the same customer, a different way through the call
VARIANTS = {
    "PUB-07b": ("PUB-07", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": ""}, {"id_reply": "answer", "id_answer": "fifth of December nineteen seventy five"},
                           {"id_reply": "answer", "id_answer": "seven zero nine three"}, {"reply": "no"}, {"reply": "vague", "date_phrase": "the week after next"},
                           {"reply": "propose", "date_phrase": "Monday the 26th"}, {"reply": "yes"}, {"reply": "yes"}]),
    "PUB-05b": ("PUB-05", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "Ninth of September nineteen ninety"}, {"id_reply": "answer", "id_answer": "Eight eight four six"},
                           {"reply": "hardship", "q_kind": "other"}, {"reply": "question", "q_kind": "other"}]),
    "PUB-06b": ("PUB-06", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "Seventeenth of May nineteen eighty six"}, {"id_reply": "answer", "id_answer": "one five zero two"},
                           {"reply": "too_much"}, {"reply": "yes", "date_phrase": "this Friday"}, {"reply": "yes"}]),
    "PUB-06c": ("PUB-06", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "17/05/1986"}, {"id_reply": "answer", "id_answer": "fifteen oh two"},
                           {"reply": "too_much"}, {"reply": "no", "q_kind": "other"}, {"reply": "yes"}, {"reply": "yes"}]),
    "PUB-01b": ("PUB-01", [{"presence": "unclear"}, {"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "the fourteenth of March"},
                           {"id_reply": "answer", "id_answer": "nineteen eighty-eight"}, {"id_reply": "answer", "id_answer": "four four"}, {"id_reply": "answer", "id_answer": "seven one"},
                           {"reply": "question", "q_kind": "scam"}, {"reply": "yes"}, {"reply": "yes"}]),
    "PUB-04b": ("PUB-04", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "30 January 1984"}, {"id_reply": "answer", "id_answer": "2219"},
                           {"reply": "propose", "date_phrase": "the sixth of November"}, {"reply": "yes", "date_phrase": "on that", "q_kind": "ai"}, {"reply": "yes"}]),
    "PUB-05c": ("PUB-05", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "9 September 1990"}, {"id_reply": "answer", "id_answer": "8846"},
                           {"reply": "hardship", "q_kind": "other"}, {"reply": "restructuring"}]),
    "PUB-02b": ("PUB-02", [{"presence": "other_person", "cb_phrase": "she is back tomorrow, call around eleven"}]),
}
# realistic customers: numbers in pieces, words for amounts and dates, self-corrections, small talk, questions back
VARIANTS.update({
    "R-01": ("PUB-01", [{"presence": "unclear", "q_kind": "other"}, {"presence": "confirmed"},
                        {"id_reply": "answer", "id_answer": "the fourteenth of March"}, {"id_reply": "answer", "id_answer": "nineteen eighty-eight"},
                        {"id_reply": "answer", "id_answer": "four four"}, {"id_reply": "answer", "id_answer": "seven one"},
                        {"reply": "question", "q_kind": "scam"}, {"reply": "other"},
                        {"reply": "propose", "amount": "four hundred and twenty", "date_phrase": "today"}, {"reply": "yes"}]),
    "R-06": ("PUB-06", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "17/05/1986"}, {"id_reply": "answer", "id_answer": "fifteen oh two"},
                        {"reply": "too_much"}, {"reply": "question", "q_kind": "other"},
                        {"reply": "propose", "date_phrase": "the twentieth, sorry, I mean this Friday"},
                        {"reply": "yes"}]),
    "R-07": ("PUB-07", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "fifth of December nineteen seventy-five"},
                        {"id_reply": "answer", "id_answer": "seven zero nine three"},
                        {"reply": "other"}, {"reply": "no"}, {"reply": "vague", "date_phrase": "after my cousin's wedding"},
                        {"reply": "propose", "date_phrase": "Monday the twenty-sixth"}, {"reply": "yes"}, {"reply": "yes"}]),
    "R-04": ("PUB-04", [{"presence": "question", "q_kind": "ai"}, {"presence": "confirmed"},
                        {"id_reply": "answer", "id_answer": "thirtieth of January nineteen eighty-four"}, {"id_reply": "answer", "id_answer": "two two", "q_kind": "none"},
                        {"id_reply": "answer", "id_answer": "one nine"}, {"reply": "propose", "date_phrase": "the sixth of November", "amount": "one thousand two hundred and fifty"},
                        {"reply": "yes"}, {"reply": "yes"}]),
    "R-10": ("PUB-10", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "23.02.1989"}, {"id_reply": "answer", "id_answer": "nine nine oh four"},
                        {"reply": "no", "q_kind": "other"}, {"reply": "yes", "q_kind": "ai"}, {"reply": "yes"}]),
    "R-10w": ("PUB-10", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "the twenty-third of February one nine eight nine", "id_iso": "1989-02-23"},
                         {"id_reply": "answer", "id_answer": "nine nine"}, {"id_reply": "answer", "id_answer": "zero four"},
                         {"reply": "no"}, {"reply": "yes"}, {"reply": "yes"}]),
    "R-07f": ("PUB-07", [{"presence": "unclear"}, {"presence": "confirmed"},
                         {"id_reply": "answer", "id_answer": "the fifth of December nineteen seventy-five"},
                         {"id_reply": "unclear"}, {"id_reply": "unclear"}, {"id_reply": "answer", "id_answer": "seven zero nine three"},
                         {"reply": "other"}, {"reply": "no"}, {"reply": "vague"}, {"reply": "propose", "date_phrase": "Monday the 26th"}, {"reply": "yes"}, {"reply": "yes"}]),
    "R-03u": ("PUB-03", [{"presence": "confirmed"}, {"id_reply": "unclear"}, {"id_reply": "unclear"}, {"id_reply": "unclear"},
                         {"id_reply": "unclear"}, {"id_reply": "unclear"}]),
    "R-frag1": ("PUB-01", [{"presence": "unclear", "message_state": "cut_off"}, {"presence": "confirmed"},
                           {"id_reply": "answer", "id_answer": "the fourteenth of", "message_state": "cut_off"}, {"id_reply": "answer", "id_answer": "March nineteen eighty-eight"},
                           {"id_reply": "unclear", "message_state": "cut_off"}, {"id_reply": "answer", "id_answer": "four four", "message_state": "cut_off"},
                           {"id_reply": "answer", "id_answer": "seven one"},
                           {"reply": "propose", "amount": "four hundred and", "message_state": "cut_off"}, {"reply": "propose", "amount": "twenty", "date_phrase": "today"},
                           {"reply": "yes"}]),
    "R-frag2": ("PUB-07", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "5 December 1975"}, {"id_reply": "answer", "id_answer": "7093"},
                           {"reply": "other", "message_state": "cut_off"}, {"reply": "no"},
                           {"reply": "propose", "date_phrase": "Monday the twenty", "message_state": "cut_off"}, {"reply": "propose", "date_phrase": "sixth"},
                           {"reply": "yes"}, {"reply": "yes"}]),
    "R-frag3": ("PUB-02", [{"presence": "other_person", "cb_phrase": "she can be reached tomorrow", "message_state": "cut_off"}, {"presence": "other_person", "cb_phrase": "at eleven"}]),
    "R-short": ("PUB-06", [{"presence": "confirmed", "message_state": "complete"}, {"id_reply": "answer", "id_answer": "17/05/1986", "message_state": "complete"},
                           {"id_reply": "answer", "id_answer": "1502", "message_state": "complete"}, {"reply": "too_much", "message_state": "complete"},
                           {"reply": "propose", "date_phrase": "friday", "message_state": "complete"}, {"reply": "yes", "message_state": "complete"}]),
    "R-shortx": ("PUB-06", [{"presence": "confirmed", "message_state": "cut_off"}, {"id_reply": "answer", "id_answer": "17/05/1986", "message_state": "cut_off"},
                            {"id_reply": "answer", "id_answer": "1502", "message_state": "cut_off"}, {"reply": "too_much", "message_state": "cut_off"},
                            {"reply": "propose", "date_phrase": "friday", "message_state": "cut_off"}, {"reply": "yes", "message_state": "cut_off"}]),
    "R-shortn": ("PUB-05", [{"presence": "confirmed", "message_state": "cut_off"}, {"id_reply": "answer", "id_answer": "9 September 1990", "message_state": "cut_off"},
                            {"id_reply": "answer", "id_answer": "8846", "message_state": "cut_off"}, {"reply": "hardship", "message_state": "cut_off"},
                            {"reply": "no", "message_state": "cut_off"}]),
    "R-03r": ("PUB-03", [{"presence": "confirmed"}, {"id_reply": "unclear"}, {"id_reply": "unclear"}, {"id_reply": "unclear"},
                         {"id_reply": "refuse"}, {"id_reply": "refuse"}]),
    "R-07t": ("PUB-07", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "5 December 1975"},
                         {"id_reply": "unclear"}, {"id_reply": "unclear"}, {"id_reply": "unclear"}, {"id_reply": "unclear"},
                         {"id_reply": "answer", "id_answer": "seven zero nine three"},
                         {"reply": "no"}, {"reply": "propose", "date_phrase": "Monday the 26th"}, {"reply": "yes"}, {"reply": "yes"}]),
    "R-07y": ("PUB-07", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "5 December 1975"}, {"id_reply": "answer", "id_answer": "7093"},
                         {"reply": "no"}, {"reply": "propose", "date_phrase": "Monday the twenty-sixth"},
                         {"reply": "yes", "date_phrase": "Tuesday the twenty", "message_state": "cut_off"}, {"reply": "other"},
                         {"reply": "yes"}]),
    "R-07z": ("PUB-07", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "5 December 1975"}, {"id_reply": "answer", "id_answer": "7093"},
                         {"reply": "no"}, {"reply": "propose", "date_phrase": "Monday the twenty-sixth"}, {"reply": "yes"},
                         {"reply": "other"}, {"reply": "other", "message_state": "cut_off"}, {"reply": "other"}, {"reply": "other"}, {"reply": "other"}, {"reply": "other"}]),
    "R-p1": ("PUB-01", [{'presence': 'confirmed'}, {'id_reply': 'answer', 'id_answer': '', 'last_message': 'The fourteenth of March.'}, {'id_reply': 'answer', 'id_answer': '1988'}, {'id_reply': 'answer', 'id_answer': '4471'}, {'reply': 'yes'}, {'reply': 'yes'}]),
    "R-p2": ("PUB-01", [{'presence': 'confirmed'}, {'id_reply': 'answer'}, {'id_reply': 'answer', 'id_answer': '14 March 1988'}, {'id_reply': 'answer', 'id_answer': '4471'}, {'reply': 'yes'}, {'reply': 'yes'}]),
    "R-p3": ("PUB-01", [{'presence': 'confirmed'}, {'id_reply': 'answer', 'id_answer': 'the fourteenth of March'}, {'id_reply': 'unclear'}, {'id_reply': 'answer', 'id_answer': '1988'}, {'id_reply': 'answer', 'id_answer': '4471'}, {'reply': 'yes'}, {'reply': 'yes'}]),
    "R-p4": ("PUB-01", [{'presence': 'confirmed'}, {'id_reply': 'answer', 'id_iso': '--03-14'}, {'id_reply': 'answer', 'id_answer': 'nineteen eighty-eight'}, {'id_reply': 'answer', 'id_answer': '4471'}, {'reply': 'yes'}, {'reply': 'yes'}]),
    "R-p5": ("PUB-01", [{'presence': 'confirmed'}, {'id_reply': 'answer', 'id_answer': 'the fourteenth of March'}, {'id_reply': 'already_given'}, {'id_reply': 'already_given'}, {'id_reply': 'answer', 'id_answer': '1988'}, {'id_reply': 'answer', 'id_answer': '4471'}, {'reply': 'yes'}, {'reply': 'yes'}]),
    "R-p6": ("PUB-01", [{'presence': 'confirmed'}, {'id_reply': 'answer', 'id_answer': '14 March 1988'}, {'id_reply': 'answer', 'id_answer': 'four four'}, {'id_reply': 'already_given', 'q_kind': 'other'}, {'id_reply': 'answer', 'id_answer': 'seven one'}, {'reply': 'yes'}, {'reply': 'yes'}]),
    "R-13": ("PUB-13", [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "eighth of January nineteen ninety-one"}, {"id_reply": "answer", "id_answer": "6604"},
                        {"reply": "propose", "date_phrase": "the thirtieth of October", "applies_to_all": "yes"}, {"reply": "question", "q_kind": "other"}, {"reply": "yes"}]),
})
for k, (base, turns) in VARIANTS.items():
    if base in CASES:
        CASES[k] = dict(CASES[base], id=k)
        SCRIPTS[k] = turns
if "PUB-01" in CASES:
    CASES["PUB-01t"] = dict(CASES["PUB-01"], id="PUB-01t", timeout_first=True)
    SCRIPTS["PUB-01t"] = SCRIPTS["PUB-01"]
if "PUB-03" in CASES:
    # five unclear answers: never a refusal; after the limit of four the call closes as the spec's 'unclear'
    CASES["R-03u"] = dict(CASES["PUB-03"], id="R-03u", expected=dict(CASES["PUB-03"]["expected"], outcome="not_reached", reason="unclear"))
    # unclear answers do not add up with refusals: two clear refusals decline, whatever came before
    CASES["R-03r"] = dict(CASES["PUB-03"], id="R-03r", expected=dict(CASES["PUB-03"]["expected"], reason="declined"))
if "PUB-07" in CASES:
    # the read-back never gets a clear yes: not confirmed, the early band has no attempt left -> refused, nothing recorded
    CASES["R-07z"] = dict(CASES["PUB-07"], id="R-07z", expected=dict(CASES["PUB-07"]["expected"], outcome="no_promise", reason="refused", promises=[]))
# PUB-06c: the floor on Friday is refused, attempt 2 of the late band offers the floor on the deadline
if "PUB-06" in CASES:
    CASES["PUB-06c"] = dict(CASES["PUB-06"], id="PUB-06c", expected=dict(CASES["PUB-06"]["expected"], promises=[{"product_id": "p1", "amount": 637.5, "date": "2026-10-23"}]))


class Bank:
    def __init__(self, case, spec=None):
        self.spec = spec or {}
        self.case, self.wrong, self.ok = case, 0, set()
        self.promises, self.notes, self.callbacks, self.transfers, self.calls = [], [], [], [], []
        self.outcome = self.reason = None
        self.fail = dict((f["tool"], f["fail_first_n"]) for f in case.get("faults") or [])

    def call(self, tool, args):
        # request fields -> roles, and the response roles -> the tool API's field names
        a = dict((self._role(tool, k), v) for k, v in args.items())
        r = self._call(tool, a)
        if not isinstance(r, dict):
            return r
        out = dict((runtime.resp_field(self.spec, tool, k), v) for k, v in r.items())
        return out

    def _role(self, tool, field):
        for f in self.spec.get("tool_fields") or []:
            if f.get("tool") == tool and f.get("field") == field:
                return f.get("role")
        return field

    def _call(self, tool, a):
        self.calls.append(tool)
        if tool == "create_promise" and self.case.get("timeout_first") and not self.calls.count(tool) > 1:
            self.promises.append((a["product_id"], round(float(a["amount"]), 2), a["date"]))
            return None
        if tool == "create_promise" and any(x[0] == a["product_id"] for x in self.promises):
            return {"ok": False, "error": "this product already has a promise"}
        if self.fail.get(tool):
            self.fail[tool] -= 1
            return {"ok": False, "error": "service unavailable, nothing was recorded"}
        if tool == "verify_identity":
            right = self.case["identity"].get(a.get("field")) == a.get("answer")
            if right:
                self.ok.add(a["field"])
            else:
                self.wrong += 1
            need = len(self.case["identity"])
            mx = int(((self.spec.get("identity") or {}).get("max_wrong_total")) or 3)
            return {"ok": True, "verified": right, "wrong_answers_left": max(0, mx - self.wrong), "all_verified": len(self.ok) >= need}
        if tool == "get_account":
            if len(self.ok) < len(self.case["identity"]):
                return {"ok": False, "error": "identity not verified"}
            pid = runtime.resp_field(self.spec, "get_account", "product_id")
            return {"ok": True, "products": [p if pid in p else dict(p, **{pid: f"p{i + 1}"}) for i, p in enumerate(self.case["products"])]}
        if tool == "create_promise":
            self.promises.append((a["product_id"], round(float(a["amount"]), 2), a["date"]))
            return {"ok": True, "promise_id": "x"}
        if tool == "add_note":
            self.notes.append((a["product_id"], a["reason"]))
            return {"ok": True}
        if tool == "schedule_callback":
            self.callbacks.append((a["date"], a["time"]))
            return {"ok": True}
        if tool == "transfer_to_agent":
            self.transfers.append(a["queue"])
            return {"ok": True}
        return {"ok": True}


def simulate(spec, case, script):
    """One call through the brain with a fake bank. Returns (bank, V, log, turns left)."""
    bank = Bank(case, spec)
    V = dict(case["variables"])
    V[(spec.get("variables") or {}).get("customer_id") or "customer_id"] = "c_x"
    script = copy.deepcopy(script)
    log = []
    for _ in range(120):
        runtime.brain(V, spec)
        ns = V.get("next_step")
        if ns.startswith("talk_"):
            log.append(("AGENT", V["say_line"] if ns.endswith("_fixed") else "[llm] " + V["instruction"]))
            if not script:
                log.append(("USER", "(hangs up)"))
                break
            turn = dict(script.pop(0))
            if "custom_reason" in turn:
                # the scripts cannot know the name the extraction chose: pick the custom situation by its reason
                want = turn.pop("custom_reason")
                turn["custom"] = next((c["name"] for c in spec.get("custom_situations") or [] if c.get("reason") == want), "none")
            log.append(("USER", json.dumps(turn)))
            V.update(turn)
        elif ns.startswith("do_"):
            tool = ns[3:]
            args = dict((k[len("a_" + tool + "_"):], v) for k, v in V.items() if k.startswith("a_" + tool + "_") and v != "")
            res = bank.call(tool, args)
            log.append(("TOOL", f"{tool} {args} -> {res}"))
            V["res_" + tool] = json.dumps(res) if res is not None else ""
        else:
            log.append(("AGENT", "[bye] " + V.get("farewell", "")))
            break
    bank.outcome, bank.reason = V.get("final_outcome") or None, V.get("final_reason") or None
    return bank, V, log, script


def compare(bank, exp):
    problems = []
    if (bank.outcome, bank.reason) != (exp["outcome"], exp.get("reason")):
        problems.append(f"outcome {(bank.outcome, bank.reason)} expected {(exp['outcome'], exp.get('reason'))}")
    if sorted(bank.promises) != sorted((p["product_id"], p["amount"], p["date"]) for p in exp["promises"]):
        problems.append(f"promises {bank.promises} expected {[(p['product_id'], p['amount'], p['date']) for p in exp['promises']]}")
    if exp.get("notes") is not None and sorted(bank.notes) != sorted((n["product_id"], n["reason"]) for n in exp["notes"]):
        problems.append(f"notes {bank.notes} expected {exp['notes']}")
    if sorted(bank.callbacks) != sorted((c["date"], c["time"]) for c in exp["callbacks"]):
        problems.append(f"callbacks {bank.callbacks} expected {exp['callbacks']}")
    if sorted(bank.transfers) != sorted(t["queue"] for t in exp["transfers"]):
        problems.append(f"transfers {bank.transfers} expected {exp['transfers']}")
    return problems


def run_case(spec, cid, verbose=False):
    case = CASES[cid]
    bank, V, log, script = simulate(spec, case, SCRIPTS[cid])
    problems = compare(bank, case["expected"])
    # the builder's own lines take turns: the same one never opens two replies in a row
    starts = [text for who, text in log if who == "AGENT"]
    for x, y in zip(starts, starts[1:]):
        for opts in runtime.VARIANTS.values():
            for o in opts:
                head = o.split("<")[0].strip()
                if len(head) > 6 and x.startswith(head) and y.startswith(head):
                    problems.append(f"same opening twice in a row: '{head}'")
    if cid in ("R-07z",) and not (log and log[-1][1].startswith("[bye]")):
        problems.append("the call did not end with the agent's own goodbye")
    if cid.startswith("R-short") and any(who == "AGENT" and text.strip() in runtime.VARIANTS["go_on"] for who, text in log):
        problems.append("'Go on.' after a short complete answer")
    if script:
        problems.append(f"{len(script)} scripted turns left unused")
    st = json.loads(V.get("st") or "{}")
    if st.get("warnings"):
        problems.append(f"warnings {st['warnings']}")
    print(("PASS" if not problems else "FAIL"), cid, case["title"])
    for p in problems:
        print("     -", p)
    if verbose or problems:
        for who, text in log:
            print(f"       {who:5} {text[:300]}")
    return not problems


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    spec = json.load(open(args[0]))
    if "--cases" in sys.argv:
        path = sys.argv[sys.argv.index("--cases") + 1]
        args = [a for a in args if a != path]
        CASES.clear(); SCRIPTS.clear()
        for c in json.load(open(path)):
            if c.get("spec") and c["spec"] not in args[0]:
                continue
            CASES[c["id"]] = c
            SCRIPTS[c["id"]] = c["script"]
    ids = args[1:] or sorted(SCRIPTS)
    ok = sum(run_case(spec, i, "-v" in sys.argv) for i in ids)
    print(f"\n{ok} / {len(ids)} passed locally")
