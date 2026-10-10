"""The builder's own test: scenarios made from the spec, run through the brain with a fake bank.

No model call and no platform call; it takes a few seconds. Every expected value is taken from the spec
(outcome table, bands, calendar, phrases), so the same code tests any brief.

    python3 builder/selftest.py out/<slot>.spec.json
"""
import datetime, json, pathlib, re, sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runtime as R
import sim_local

D = datetime.date


def _rf(S, tool, role):
    return R.resp_field(S, tool, role)


def _now(S):
    """A business day a few days before the first holiday, so that a holiday falls inside the deadlines."""
    hol = sorted((S.get("calendar") or {}).get("holidays") or [])
    day = D.fromisoformat(hol[0]) - datetime.timedelta(days=3) if hol else D(2030, 3, 12)
    for _ in range(14):
        if R.is_bday(S, day):
            break
        day -= datetime.timedelta(days=1)
    return datetime.datetime.combine(day, datetime.time(11, 0))


def _answer(q):
    t = q.get("answer_type")
    if t == "date":
        return "1980-01-15", "1980-01-15"
    if t == "digits":
        n = int(q.get("digits_length") or 4)
        v = ("1234567890" * 2)[:n]
        return v, v
    if t == "year":
        return "1980", "1980"
    return "AB1 2CD", "AB1 2CD"


def _product(S, i, ptype, days_late):
    p = {_rf(S, "get_account", "product_id"): f"p{i + 1}", _rf(S, "get_account", "type"): ptype["type"],
         _rf(S, "get_account", "past_due"): 500.0 + 100 * i, _rf(S, "get_account", "days_late"): days_late}
    if ptype.get("floor_field"):
        p[ptype["floor_field"]] = 150.0 + 10 * i
    for name in re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", ptype.get("spoken_template") or ""):
        p.setdefault(name, "4321")
    return p


def _out(S, situation):
    o, r = R.outcome_for(S, situation)
    return o or None, r or None


def _case(S, name, products, script, expected, now, faults=None):
    vars_ = (S.get("variables") or {})
    v = dict((k, "Test") for k in vars_.get("all") or [])
    v[vars_.get("now") or "now"] = now.strftime("%Y-%m-%dT%H:%M")
    ident = dict((q["field"], _answer(q)[1]) for q in R.questions(S))
    return {"id": name, "variables": v, "identity": ident, "products": products, "faults": faults or [],
            "script": script, "expected": expected}


def _exp(S, situation, promises=(), callbacks=(), transfers=(), notes=None):
    o, r = _out(S, situation)
    return {"outcome": o, "reason": r, "promises": list(promises), "callbacks": list(callbacks),
            "transfers": [{"queue": q} for q in transfers], "notes": notes}


def _notes_for(S, pids, situation):
    """Notes expected for products without a promise, when the brief uses notes."""
    if not R.notes_enabled(S):
        return []
    reason = R.note_reason(S, situation)
    return [{"product_id": p, "reason": reason} for p in pids] if reason else []


def scenarios(S):
    now = _now(S)
    today = now.date()
    qs = R.questions(S)
    login = [{"presence": "confirmed"}] + [{"id_reply": "answer", "id_answer": _answer(q)[0]} for q in qs]
    types = [p for p in S.get("products") or [] if p.get("type")] or [{"type": "product", "spoken_template": "account", "floor_field": ""}]
    bands = S.get("bands") or [{"name": "default", "days_late_min": 1, "days_late_max": 30, "attempts": 1}]
    out = []

    def one(i=0, band=None):
        b = band or bands[0]
        late = (int(b.get("days_late_min") or 1) + int(b.get("days_late_max") or 1)) // 2
        return _product(S, i, types[i % len(types)], late)

    def plan(p):
        return R.plan_products(S, [p], today)[0]

    p = one()
    pl = plan(p)
    out.append(_case(S, "happy path: pays in full today", [p], login + [{"reply": "yes"}, {"reply": "yes"}],
                     _exp(S, "promise_recorded", [{"product_id": "p1", "amount": pl["due"], "date": today.isoformat()}], notes=[]), now))

    for b in bands:
        p = one(0, b)
        attempts = int(b.get("attempts") or 1)
        out.append(_case(S, f"band {b.get('name')}: refuses every offer ({attempts} attempts)", [p], login + [{"reply": "no"}] * (attempts + 1),
                         _exp(S, "refused", notes=_notes_for(S, ["p1"], "refused")), now))

    p = one()
    pl = plan(p)
    far = today + datetime.timedelta(days=120)
    out.append(_case(S, "a date after the deadline: the deadline is offered", [p],
                     login + [{"reply": "propose", "date_phrase": far.isoformat()}, {"reply": "yes"}, {"reply": "yes"}],
                     _exp(S, "promise_recorded", [{"product_id": "p1", "amount": pl["due"], "date": pl["deadline"]}], notes=[]), now))

    hol = [h for h in (S.get("calendar") or {}).get("holidays") or [] if today < D.fromisoformat(h) <= D.fromisoformat(pl["deadline"])]
    if hol:
        ok_d, _ = R.check_date(S, pl, D.fromisoformat(hol[0]), today)
        out.append(_case(S, f"a holiday ({hol[0]}) inside the deadline", [p],
                         login + [{"reply": "propose", "date_phrase": hol[0]}, {"reply": "yes"}, {"reply": "yes"}],
                         _exp(S, "promise_recorded", [{"product_id": "p1", "amount": pl["due"], "date": ok_d.isoformat()}], notes=[]), now))

    if qs:
        mx = int((S.get("identity") or {}).get("max_wrong_total") or 3)
        wrong = [{"presence": "confirmed"}] + [{"id_reply": "answer", "id_answer": "1901-01-01" if qs[0].get("answer_type") == "date" else "0000" if qs[0].get("answer_type") in ("digits", "year") else "ZZ9 9ZZ"}] * mx
        out.append(_case(S, f"{mx} wrong security answers", [one()], wrong, _exp(S, "id_failed", notes=[]), now))

    tp = S.get("third_party") or {}
    if tp.get("callback_enabled", True):
        days = R.allowed_callback_days(S, now)
        day = days[-1]
        tm = tp.get("window_start") or "12:00"
        if day == today and tm <= now.strftime("%H:%M"):
            tm = tp.get("window_end") or "23:00"
        out.append(_case(S, "someone else answers and gives a callback time", [one()],
                         [{"presence": "other_person", "cb_phrase": f"{day.isoformat()} at {tm}"}],
                         _exp(S, "callback", callbacks=[{"date": day.isoformat(), "time": tm}], notes=[]), now))

    rq = S.get("requests") or {}
    if (rq.get("already_paid") or {}).get("enabled", True):
        out.append(_case(S, "says they already paid", [one()], login + [{"reply": "already_paid"}],
                         _exp(S, "already_paid", notes=_notes_for(S, ["p1"], "already_paid")), now))
    if (rq.get("dispute") or {}).get("enabled", True):
        out.append(_case(S, "says the debt is not theirs", [one()], login + [{"reply": "dispute"}],
                         _exp(S, "dispute", notes=_notes_for(S, ["p1"], "dispute")), now))
    if (rq.get("restructuring") or {}).get("enabled", True) and R.queue_for(S, "restructuring"):
        out.append(_case(S, "asks for a new payment plan", [one()], login + [{"reply": "restructuring"}],
                         _exp(S, "transfer_restructuring", transfers=[R.queue_for(S, "restructuring")], notes=[]), now))
    hm = rq.get("human") or {}
    if hm.get("enabled", True) and R.queue_for(S, "human"):
        n = int(hm.get("ask_help_first_times") or 0) + 1
        out.append(_case(S, "insists on a human", [one()], login + [{"reply": "human"}] * n,
                         _exp(S, "transfer_human", transfers=[R.queue_for(S, "human")], notes=[]), now))
    hs = S.get("hardship") or {}
    if hs.get("enabled", True):
        if hs.get("offer_transfer", True) and R.queue_for(S, "hardship"):
            out.append(_case(S, "hardship, accepts the transfer", [one()], login + [{"reply": "hardship"}, {"reply": "yes"}],
                             _exp(S, "transfer_support", transfers=[R.queue_for(S, "hardship")], notes=[]), now))
            out.append(_case(S, "hardship, declines the transfer", [one()], login + [{"reply": "hardship"}, {"reply": "no"}],
                             _exp(S, "hardship", notes=_notes_for(S, ["p1"], "hardship")), now))
        else:
            out.append(_case(S, "hardship", [one()], login + [{"reply": "hardship"}], _exp(S, "hardship", notes=_notes_for(S, ["p1"], "hardship")), now))

    retries = int((S.get("promise") or {}).get("retries") or 1)
    out.append(_case(S, f"the promise service fails {retries + 1} times", [one()], login + [{"reply": "yes"}, {"reply": "yes"}],
                     _exp(S, "service_error", notes=_notes_for(S, ["p1"], "service_error")), now,
                     faults=[{"tool": "create_promise", "fail_first_n": retries + 1}]))

    for c in S.get("custom_situations") or []:
        if c.get("continue_for_promise") or c.get("needs_callback"):
            continue
        pre = c.get("applies_when") == "before_verification"
        script = ([{"presence": "confirmed", "custom": c["name"]}] if pre else login + [{"reply": "other", "custom": c["name"]}])
        o, r = c.get("outcome"), c.get("reason")
        out.append(_case(S, f"the brief's own situation: {c['name']}", [one()], script,
                         {"outcome": o or None, "reason": r or None, "promises": [], "callbacks": [], "transfers": [], "notes": None}, now))

    mp = S.get("multi_product") or {}
    if mp.get("enabled") and len(bands) > 1:
        ps = [one(0, bands[0]), one(1, bands[-1])]
        pls = R.plan_products(S, ps, today)
        dls = sorted(D.fromisoformat(x["deadline"]) for x in pls)
        target = dls[-1]
        if target > dls[0] and R.is_bday(S, target):
            prom = [{"product_id": x["id"], "amount": x["due"], "date": min(target, D.fromisoformat(x["deadline"])).isoformat()} for x in pls]
            out.append(_case(S, "two products, one date after one deadline", ps,
                             login + [{"reply": "propose", "date_phrase": target.isoformat(), "applies_to_all": "yes"}, {"reply": "yes"}],
                             _exp(S, "promise_recorded", prom, notes=[]), now))
    return out


def run(spec):
    """Returns a list of {name, pass, problems}. Never raises."""
    results = []
    try:
        cases = scenarios(spec)
    except Exception as e:
        return [{"name": "making the scenarios", "pass": False, "problems": [repr(e)]}]
    for c in cases:
        try:
            bank, V, log, left = sim_local.simulate(spec, c, c["script"])
            problems = sim_local.compare(bank, c["expected"])
            st = json.loads(V.get("st") or "{}")
            problems += [f"warning: {w}" for w in st.get("warnings") or []]
        except Exception as e:
            problems = [f"crash: {e!r}"]
        results.append({"name": c["id"], "pass": not problems, "problems": problems})
    return results


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1]))
    res = run(spec)
    for r in res:
        print("PASS" if r["pass"] else "FAIL", r["name"])
        for p in r["problems"]:
            print("     -", p)
    print(f"\n{sum(r['pass'] for r in res)} / {len(res)} self-test scenarios passed")
