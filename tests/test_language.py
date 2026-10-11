"""The call's language: the builder's own lines, dates and amounts follow the spec's language; the logic does not change;
the extraction writes day, time and answer words in plain English only for a call that is not in English. No API call.

    python3 tests/test_language.py
"""
import copy, datetime, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))
import render, runtime, selftest, sim_local


def main():
    ok = True

    def check(cond, what):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + what)
        ok = ok and cond

    en = json.load(open(ROOT / "out" / "brief-a.spec.json"))
    tr = copy.deepcopy(en)
    tr["language"] = "tr"

    runtime.LANG[0] = runtime.lang_of(tr)
    check(runtime.fmt_date(datetime.date(2026, 10, 16)) == "16 Ekim Cuma", "a Turkish date: 16 Ekim Cuma")
    check(runtime.fmt_date(datetime.date(2027, 1, 4), datetime.date(2026, 10, 14)) == "4 Ocak 2027 Pazartesi", "a Turkish date in another year")
    check(runtime.fmt_amount(2125.1) == "2.125,10" and runtime.fmt_amount(1320) == "1.320", "Turkish amounts: 2.125,10 and 1.320")
    check(runtime.variant({}, "go_on") == "Devam edin." and runtime.own_line("one_at_a_time") == "Tek tek ilerleyelim.", "Turkish lines of the builder")
    runtime.LANG[0] = runtime.lang_of(en)
    check(runtime.fmt_date(datetime.date(2026, 10, 16)) == "Friday 16 October" and runtime.fmt_amount(2125.1) == "2,125.10", "English as before")
    check(runtime.lang_of({"language": "Türkçe"}) == "tr" and runtime.lang_of({"language": "de"}) == "en" and runtime.lang_of({}) == "en",
          "the language code: tr, and English for a language the builder does not know")

    # the same customers end the same way in either language; the Turkish call says the builder's lines in Turkish
    for cid in ("PUB-01", "PUB-04", "PUB-06c", "PUB-07", "R-frag1", "R-07z"):
        b1, _, log1, _ = sim_local.simulate(en, sim_local.CASES[cid], sim_local.SCRIPTS[cid])
        b2, _, log2, _ = sim_local.simulate(tr, sim_local.CASES[cid], sim_local.SCRIPTS[cid])
        same = (b1.outcome, b1.reason, sorted(b1.promises), sorted(b1.notes)) == (b2.outcome, b2.reason, sorted(b2.promises), sorted(b2.notes))
        check(same, f"{cid}: the same outcome and records in English and in Turkish")
    _, _, log, _ = sim_local.simulate(tr, sim_local.CASES["PUB-06c"], sim_local.SCRIPTS["PUB-06c"])
    said = " ".join(t for who, t in log if who == "AGENT")
    check("Ekim" in said and "2.125,10" in said and "October" not in said, "the Turkish call says dates and amounts the Turkish way")
    _, _, log, _ = sim_local.simulate(tr, sim_local.CASES["R-frag1"], sim_local.SCRIPTS["R-frag1"])
    check(any(who == "AGENT" and t in runtime.VARIANTS_TR["go_on"] for who, t in log) and not any(who == "AGENT" and t in runtime.VARIANTS["go_on"] for who, t in log),
          "a cut-off message gets the Turkish 'go on'")
    res = selftest.run(tr)
    check(all(r["pass"] for r in res), f"self-test of the Turkish spec: {sum(r['pass'] for r in res)}/{len(res)}")

    # the extraction: plain English day words only when the call is not in English
    def descriptions(spec):
        return json.dumps([render._extraction(spec, ph) for ph in ("talk_pre", "talk_id", "talk_main")])
    check(render.NOT_ENGLISH_DAYS not in descriptions(en) and render.NOT_ENGLISH_ANSWER not in descriptions(en), "English: the extraction as before")
    d = descriptions(tr)
    check(d.count("The customer does not speak English") == 3 and "write a date as day, English month name and year" in d,
          "Turkish: day words, callback words and identity answers in plain English")

    print("\nall passed" if ok else "\nSOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
