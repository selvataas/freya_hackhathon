"""Parsing corrections, numbers said again or in parts, callback days and times, and spec lines written as instructions
to the agent. No API call; the specs come from out/ (build them first with --dry --no-llm).

    python3 tests/test_runtime_fixes.py
"""
import copy, datetime, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))
import render, runtime, sim_local

D = datetime.date


def main():
    ok = True

    def check(cond, what):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + what)
        ok = ok and cond

    spec = json.load(open(ROOT / "out" / "brief-a.spec.json"))
    today = D(2026, 10, 14)

    # corrections: what comes after 'sorry, I mean' replaces only what it names
    check(runtime.parse_dob("the eighteenth, sorry, I mean the nineteenth of October nineteen eighty three", "DMY") == ("ok", "1983-10-19"),
          "date of birth: a corrected day")
    check(runtime.parse_dob("19 November 1983, sorry, I mean October", "DMY") == ("ok", "1983-10-19"), "date of birth: only the month corrected")
    check(runtime.parse_dob("31/02/1983, sorry, I mean 19/10/1983", "DMY") == ("ok", "1983-10-19"), "date of birth: an impossible date corrected")
    check(runtime.parse_dob("14 March 1988", "DMY") == ("ok", "1988-03-14") and runtime.parse_dob("17/05/1986", "DMY") == ("ok", "1986-05-17"),
          "date of birth without a correction: as before")
    check(runtime.parse_dob("the fourteenth of March", "DMY") == ("partial", None) and runtime.parse_dob("31/02/1983", "DMY") == ("bad", None),
          "date of birth: a part is partial, an impossible date is bad")
    digits = {"answer_type": "digits", "digits_length": 4}
    check(runtime.normalize_answer(digits, "four four one seven, sorry, I mean four four seven one", "") == ("ok", "4471"), "digits corrected")
    check(runtime.normalize_answer({"answer_type": "year"}, "1979, sorry, I mean 1980", "") == ("ok", "1980"), "a year corrected")
    check(runtime.normalize_answer({"answer_type": "text"}, "N4 7QY, sorry, I mean N4 7QX", "") == ("ok", "N4 7QX"), "a text answer corrected")
    check(runtime.normalize_answer({"answer_type": "text"}, " N4 7QX ", "") == ("ok", "N4 7QX"), "a text answer without a correction: as before")
    check(runtime.spoken_amount("two hundred, sorry, I mean two hundred and fifty") == 250.0, "an amount corrected")
    check(runtime.spoken_amount("455.50") == 455.5 and runtime.spoken_amount("") is None, "an amount without a correction: as before")
    check(runtime.callback_when(spec, "tomorrow at 11, sorry, I mean 12", today) == (D(2026, 10, 15), "12:00"), "callback: the time corrected, the day kept")
    check(runtime.callback_when(spec, "tomorrow at 3 pm, no wait, today", today) == (today, "15:00"), "callback: the day corrected, the time kept")
    # a number said as a time is not a day of the month
    check(runtime.callback_when(spec, "she is back at 3 pm", today) == (None, "15:00"), "callback: 'at 3 pm' is a time, not the 3rd")
    check(runtime.callback_when(spec, "11:00", today) == (None, "11:00"), "callback: '11:00' is a time, not the 11th")
    check(runtime.callback_when(spec, "tomorrow morning around eleven", today) == (D(2026, 10, 15), "11:00"), "callback: day and time as before")
    check(runtime.callback_when(spec, "at 11 on the 16th", today) == (D(2026, 10, 16), "11:00"), "callback: the day is the 16th, not the 11th")
    check(runtime.parse_time("tonight after nine") == "21:00", "'tonight after nine' is 21:00")

    # a number said again from the start, and a number said in two parts
    four = {"answer_type": "digits", "digits_length": 4}
    five = {"answer_type": "digits", "digits_length": 5}
    free = {"answer_type": "digits", "digits_length": None}
    check(runtime.restarts(four, "44", "440") and runtime.restarts(four, "four four", "four four seven one"), "'44' then '440' starts again")
    check(not runtime.restarts(five, "463", "51") and not runtime.restarts(free, "463", "51"), "'463' then '51' is a second part")
    check(not runtime.restarts(four, "44", "44"), "'44' then '44' is a second part (4444)")

    def identity_call(length, said, right):
        """One verification through the brain, the phone question set to the given length."""
        s = copy.deepcopy(spec)
        s["identity"]["questions"][1]["digits_length"] = length
        case = copy.deepcopy(sim_local.CASES["PUB-01"])
        case["identity"]["phone_last4"] = right
        script = [{"presence": "confirmed"}, {"id_reply": "answer", "id_answer": "14 March 1988"}]
        script += [{"id_reply": "answer", "id_answer": x, "message_state": "cut_off"} for x in said[:-1]]
        script += [{"id_reply": "answer", "id_answer": said[-1]}, {"reply": "yes"}, {"reply": "yes"}]
        bank, V, log, left = sim_local.simulate(s, case, script)
        sent = [t for who, t in log if who == "TOOL" and t.startswith("verify_identity") and "phone_last4" in t]
        return bank, sent
    bank, sent = identity_call(5, ["463", "51"], "46351")
    check(bank.wrong == 0 and bank.outcome == "promise" and len(sent) == 1 and "'46351'" in sent[0], "5 digits said as '463' then '51': one answer, 46351")
    bank, sent = identity_call(None, ["463", "51"], "46351")
    check(bank.wrong == 0 and len(sent) == 1 and "'46351'" in sent[0], "digits of no fixed length as '463' then '51': 46351")
    bank, sent = identity_call(4, ["44", "440", "4410"], "4410")
    check(bank.wrong == 0 and len(sent) == 1 and "'4410'" in sent[0], "'44', then '440', then '4410': one answer, 4410, no wrong answer")
    bank, sent = identity_call(4, ["44", "10"], "4410")
    check(bank.wrong == 0 and len(sent) == 1 and "'4410'" in sent[0], "'44' then '10': one answer, 4410")

    # spec lines written as instructions to the agent become lines for the customer
    turns = {
        "Ask the customer to say the month of their date of birth as a word.": "Could you say the month of your date of birth as a word?",
        "Ask the customer to give the month in words.": "Could you give the month in words?",
        "Tell the customer that payments can take one business day to appear.": "Payments can take one business day to appear.",
        "Tell them to use the mobile app or a branch.": "Please use the mobile app or a branch.",
        "Ask the customer when they can pay.": "Could you tell me when you can pay?",
        "Ask the caller for the exact day.": "Could you give me the exact day?",
        "Offer to connect them with the customer support team.": "Would you like me to connect you with the customer support team?",
        'Say "I am sorry for your loss."': "I am sorry for your loss.",
        "Let the customer know that you are a digital assistant.": "I am a digital assistant.",
        "Inform the customer that you cannot record that amount. Ask them to pick another day.": "I cannot record that amount. Could you pick another day?",
    }
    for a, b in turns.items():
        got = render.instruction_to_line(a)
        check(got == b, f"instruction turned: {a!r} -> {got!r}")
    for t in ["Could you tell me your date of birth?", "Please tell us your date of birth.", "Say your date of birth, please.",
              "Am I speaking with <address>?", "When would be a good time to reach <address>?", "I am sorry for your loss."]:
        check(render.instruction_to_line(t) is None, f"a line for the customer is left as it is: {t!r}")
    s = copy.deepcopy(spec)
    s["phrases"]["condolence"] = {"text": "Tell them that we are sorry.", "verbatim": True}
    s["phrases"]["no_info"] = {"text": "Tell the customer that you do not have that information.", "verbatim": False}
    s["custom_situations"] = [{"name": "x", "say_text": "Ask the customer to call back later.", "verbatim": True},
                              {"name": "y", "say_text": "Ask the customer to call back later.", "verbatim": False}]
    out, changes = render.customer_lines(s)
    check(out["phrases"]["condolence"]["text"] == "Tell them that we are sorry.", "a verbatim phrase is never touched")
    check(out["phrases"]["no_info"]["text"] == "I do not have that information.", "a non-verbatim phrase is turned")
    check(out["custom_situations"][0]["say_text"] == "Ask the customer to call back later.", "a verbatim custom line is never touched")
    check(out["custom_situations"][1]["say_text"] == "Could you call back later?", "a non-verbatim custom line is turned")
    check(out["identity"]["hints"][0]["instruction"].startswith("Could you"), "the hint line is turned")
    check(s["phrases"]["no_info"]["text"].startswith("Tell"), "the spec given in is not changed")

    print("\nall passed" if ok else "\nSOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
