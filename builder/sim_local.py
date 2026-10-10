"""Run the brain against scripted customers and a fake bank, without the platform. A development check.

    .venv/bin/python builder/sim_local.py out/brief-a.spec.json [case_id ...] [-v]

Each script turn is what the extraction model would produce for one customer message.
"""
import copy, json, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runtime

CASES = {c["id"]: c for c in json.load(open(HERE.parent / "public-test-set.json"))}

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
for k, (base, turns) in VARIANTS.items():
    CASES[k] = dict(CASES[base], id=k)
    SCRIPTS[k] = turns
CASES["PUB-01t"] = dict(CASES["PUB-01"], id="PUB-01t", timeout_first=True)
SCRIPTS["PUB-01t"] = SCRIPTS["PUB-01"]
# PUB-06c: the floor on Friday is refused, attempt 2 of the late band offers the floor on the deadline
CASES["PUB-06c"] = dict(CASES["PUB-06"], id="PUB-06c", expected=dict(CASES["PUB-06"]["expected"], promises=[{"product_id": "p1", "amount": 637.5, "date": "2026-10-23"}]))


class Bank:
    def __init__(self, case):
        self.case, self.wrong, self.ok = case, 0, set()
        self.promises, self.notes, self.callbacks, self.transfers, self.calls = [], [], [], [], []
        self.outcome = self.reason = None
        self.fail = dict((f["tool"], f["fail_first_n"]) for f in case.get("faults") or [])

    def call(self, tool, a):
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
            r = {"ok": True, "verified": right, "wrong_answers_left": max(0, 3 - self.wrong), "all_verified": len(self.ok) >= 2}
            return r
        if tool == "get_account":
            if len(self.ok) < 2:
                return {"ok": False, "error": "identity not verified"}
            return {"ok": True, "products": [dict(p, product_id=f"p{i + 1}") for i, p in enumerate(self.case["products"])]}
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


def run_case(spec, cid, verbose=False):
    case = CASES[cid]
    bank = Bank(case)
    V = dict(case["variables"], customer_id="c_x")
    script = copy.deepcopy(SCRIPTS[cid])
    log = []
    for _ in range(80):
        runtime.brain(V, spec)
        ns = V.get("next_step")
        if ns.startswith("talk_"):
            log.append(("AGENT", V["say_line"] if ns.endswith("_fixed") else "[llm] " + V["instruction"]))
            if not script:
                log.append(("USER", "(hangs up)"))
                break
            turn = script.pop(0)
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
    exp = case["expected"]
    problems = []
    if (bank.outcome, bank.reason) != (exp["outcome"], exp.get("reason")):
        problems.append(f"outcome {(bank.outcome, bank.reason)} expected {(exp['outcome'], exp.get('reason'))}")
    if sorted(bank.promises) != sorted((p["product_id"], p["amount"], p["date"]) for p in exp["promises"]):
        problems.append(f"promises {bank.promises} expected {[(p['product_id'], p['amount'], p['date']) for p in exp['promises']]}")
    if sorted(bank.notes) != sorted((n["product_id"], n["reason"]) for n in exp["notes"]):
        problems.append(f"notes {bank.notes} expected {exp['notes']}")
    if sorted(bank.callbacks) != sorted((c["date"], c["time"]) for c in exp["callbacks"]):
        problems.append(f"callbacks {bank.callbacks} expected {exp['callbacks']}")
    if sorted(bank.transfers) != sorted(t["queue"] for t in exp["transfers"]):
        problems.append(f"transfers {bank.transfers} expected {exp['transfers']}")
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
    ids = args[1:] or sorted(SCRIPTS)
    ok = sum(run_case(spec, i, "-v" in sys.argv) for i in ids)
    print(f"\n{ok} / {len(ids)} passed locally")
