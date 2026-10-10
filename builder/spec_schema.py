"""The fixed spec schema the LLM fills from a brief, the builder's own vocabularies, and normalize().

Nothing in this file comes from a brief. The vocabularies are the builder's words for situations and dates;
the LLM maps whatever a brief calls them onto these words.
"""
import copy, re

SCHEMA_VERSION = "9"

SITUATIONS = ["promise_recorded", "already_paid", "transfer_restructuring", "transfer_human", "transfer_support",
              "refused", "hardship", "dispute", "service_error", "id_failed", "id_declined", "callback",
              "no_callback", "wrong_number", "deceased", "unclear"]
NOTE_SITUATIONS = ["refused", "hardship", "dispute", "already_paid", "service_error"]
DEADLINE_UNITS = ["business_days", "calendar_days", "end_of_month"]
NAMED_DATES = ["today", "tomorrow", "end_of_this_week", "end_of_next_week", "next_business_day", "deadline"]
ATTEMPT_AMOUNTS = ["full", "floor", "full_or_floor_if_too_much"]
ANSWER_TYPES = ["date", "digits", "year", "text"]
DATE_ORDERS = ["DMY", "MDY", "YMD"]
NEXT_WEEKDAY = ["following_week", "next_occurrence"]
CUSTOM_WHEN = ["before_verification", "after_verification", "any"]
CALLBACK_DAYS = ["today_or_next_business_day", "today_only", "next_business_day_only", "business_days_within_n"]
NON_BUSINESS = ["offer_next_business_day", "offer_previous_business_day"]
EARLIEST = ["today", "tomorrow"]

# role vocabularies for the seven tools; the spec maps each role to the field name the tool API uses
TOOL_ROLES = {
    "verify_identity": ["customer_id", "field", "answer"],
    "get_account": ["customer_id"],
    "create_promise": ["customer_id", "product_id", "amount", "date"],
    "add_note": ["customer_id", "product_id", "reason", "text"],
    "schedule_callback": ["customer_id", "date", "time"],
    "transfer_to_agent": ["customer_id", "queue"],
    "close_call": ["customer_id", "outcome", "reason"],
}
RESPONSE_ROLES = {
    "verify_identity": ["ok", "verified", "wrong_answers_left", "all_verified", "hint"],
    "get_account": ["ok", "products", "product_id", "type", "past_due", "days_late"],
    "create_promise": ["ok"], "add_note": ["ok"], "schedule_callback": ["ok"], "transfer_to_agent": ["ok"], "close_call": ["ok"],
}

# What each phrase is for. <placeholders> in angle brackets are filled by the runtime.
PHRASES = {
    "opening": "First sentence of the call, said before anything else.",
    "identity_question": "Asks whether the agent is speaking with the customer. Use <address> for how the customer is addressed.",
    "condolence": "Said when the person says the customer has died.",
    "wrong_number_ack": "Said when the number does not belong to the customer, before goodbye.",
    "third_party_ask": "Asks someone else on the line when the customer can be reached. Use <address>.",
    "no_callback": "Said when no callback time inside the allowed window was found.",
    "callback_confirm": "Confirms a booked callback. Use <date> and <time>.",
    "decline_explain": "Explains once why the security questions are asked, when the customer does not want to answer.",
    "id_failed": "Said after the identity check failed for good (for example: where the customer can go instead).",
    "ai_answer": "Answer when the customer asks whether they talk to a robot or an AI.",
    "scam_answer": "Answer when the customer asks whether the call is a scam.",
    "no_info": "Answer to a question the agent cannot answer from the tools.",
    "human_offer_help": "Asked once when the customer wants a human, before transferring.",
    "transfer_announce": "Said when the call is handed to a person.",
    "debt_intro": "First sentence after identity is verified: who is calling and why.",
    "debt_line": "One sentence per late product. Use <product>, <amount> and <days>.",
    "pay_today": "The first ask for one product.",
    "pay_all_today": "The first ask when there are several products.",
    "floor_caveat": "Said when offering the lower amount because the full amount is too much. Use <amount>.",
    "clamp_note": "Said in the read-back when one product moves to its own latest date. Use <product> and <date>.",
    "confirm_question": "The question after reading back the promises.",
    "after_promise": "Said after a promise is recorded.",
    "changes_after_record": "Said when the customer wants to change a promise that is already recorded.",
    "already_paid": "Said when the customer says they already paid.",
    "dispute_ack": "Said when the customer says the debt is not theirs, without arguing.",
    "hardship_sympathy": "One short sentence of sympathy for the hardship situations the brief names.",
    "hardship_offer_transfer": "Offers to connect the customer with the team that helps in hardship.",
    "service_error": "Said when a promise could not be recorded after the retries. Use <product>.",
    "goodbye": "Thanks the customer and says goodbye. Said last in every call.",
    "not_understood": "Said when the agent did not catch the answer, before asking again.",
    "purpose_answer": "Answer when the customer asks what the call is about before identity is verified. Gives no reason for the call.",
    "third_party_privacy": "Said to someone else on the line who asks what the call is about. Gives no reason. Use <address>.",
    "ask_rest": "Asks for the rest of an answer the customer gave only in part.",
    "wrong_answer": "Said after a wrong security answer, before asking the same question again. Never reveals the right answer.",
    "unreadable_answer": "Said when the security answer could not be read, before asking again.",
    "ask_callback_time": "Asks someone else on the line at what time on <date> <address> can be reached.",
    "callback_other_time": "Says a callback is possible on <days> between <start> and <end>, and asks for another time.",
    "not_talking_ack": "Acknowledges that the customer does not want to talk, before asking once more.",
    "offer": "Proposes a payment. Use <amount>, <for_product> (empty for one product) and <when> (e.g. 'today' or 'on Friday 16 October'). A question.",
    "for_product": "The words that name the product inside an offer, e.g. 'for your <product>'.",
    "word_today": "The word for today inside a sentence, e.g. 'today'.",
    "word_on_date": "The words for a day inside a sentence, e.g. 'on <date>'.",
    "promise_item": "One promise inside a read-back or confirmation. Use <amount>, <product> and <when>.",
    "readback": "Reads the promises back. Use <items>. The confirmation question follows separately.",
    "recorded": "Says the promises are recorded. Use <items>. Said only after the bank confirmed the recording.",
    "ask_exact_day": "Asks once for the exact day after the customer named only a vague period.",
    "ask_day_for_amount": "Asks on which day the customer can pay <amount>.",
    "latest_date": "Says the latest date that can be recorded is <date>.",
    "not_business_day": "Says <date> is not a business day and the next business day is <next>.",
    "past_date": "Says the day has passed and asks for a day from today on.",
    "below_floor": "Says the proposed amount cannot be recorded and the lowest amount that can be recorded is <amount>.",
}


def S(t, d=None, enum=None):
    x = {"type": t}
    if enum:
        x["enum"] = enum
    if d:
        x["description"] = d
    return x


def N(t, d=None, enum=None):
    """Nullable."""
    inner = S(t, None, enum)
    return {"anyOf": [inner, {"type": "null"}], "description": d} if d else {"anyOf": [inner, {"type": "null"}]}


def O(props, d=None):
    x = {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}
    if d:
        x["description"] = d
    return x


def A(items, d=None):
    x = {"type": "array", "items": items}
    if d:
        x["description"] = d
    return x


PHRASE = O({"text": S("string"), "verbatim": S("boolean", "true only if the brief gives this exact wording in quotes")})

SCHEMA = O({
    "language": S("string", "Language the agent speaks, e.g. en."),
    "bank_name": S("string"),
    "variables": O({
        "customer_id": S("string", "Name of the call variable holding the customer id."),
        "now": S("string", "Name of the call variable holding the current date and time."),
        "address_template": S("string", "How to address the customer, with call variable names in curly braces, e.g. {title} {last_name}."),
        "all": A(S("string"), "Every call variable the brief lists."),
    }),
    "phrases": O(dict((k, dict(PHRASE, description=v)) for k, v in PHRASES.items())),
    "forbidden": O({
        "before_verification": A(S("string"), "Words or topics the agent must not say before identity is verified."),
        "offers": A(S("string"), "Things the agent must never offer."),
        "questions": A(S("string"), "Questions the agent must never ask."),
    }),
    "presence": O({"max_asks": S("integer", "How many times the agent asks whether it speaks with the customer before closing as unclear.")}),
    "third_party": O({
        "callback_enabled": S("boolean"),
        "callback_days": S("string", "Which days a callback may be on.", CALLBACK_DAYS),
        "callback_days_n": S("integer", "Only for business_days_within_n."),
        "window_start": S("string", "HH:MM, inclusive."),
        "window_end": S("string", "HH:MM, inclusive."),
        "after_now": S("boolean", "The callback must be later than now."),
        "max_asks": S("integer", "How many times a time is asked for in total before giving up, including the first."),
    }),
    "identity": O({
        "questions": A(O({
            "field": S("string", "The value the tool API expects for this question (an enum value of verify_identity)."),
            "ask_text": S("string", "The question, as the agent says it."),
            "answer_type": S("string", None, ANSWER_TYPES),
            "digits_length": N("integer", "For digits answers: how many digits."),
            "numeric_date_order": S("string", "How a date given only as numbers is read.", DATE_ORDERS),
        }), "In the order they are asked."),
        "max_wrong_total": S("integer", "Wrong answers in total that end the check."),
        "hints": A(O({
            "value": S("string", "A hint value the tool can return."),
            "instruction": S("string", "What the agent says or asks when it comes back."),
            "counts_as_wrong": S("boolean"),
        })),
        "max_refusals": S("integer", "Refusals to answer that close the call as declined."),
        "purpose_question_is_refusal": S("boolean", "Asking what the call is about instead of answering counts as a refusal."),
    }),
    "calendar": O({
        "business_weekdays": A(S("integer"), "0 = Monday ... 6 = Sunday."),
        "holidays": A(S("string"), "YYYY-MM-DD."),
        "next_weekday": S("string", "'next <weekday>': following_week = that weekday in the following calendar week.", NEXT_WEEKDAY),
        "numeric_date_order": S("string", None, DATE_ORDERS),
    }),
    "products": A(O({
        "type": S("string", "A product type value from get_account."),
        "spoken_template": S("string", "How the product is named in words, with get_account field names in curly braces, e.g. 'savings account ending {last4}'."),
        "floor_field": S("string", "The get_account field that holds the lowest amount that may be accepted for this type."),
    })),
    "bands": A(O({
        "name": S("string"),
        "days_late_min": S("integer"), "days_late_max": S("integer"),
        "deadline_unit": S("string", None, DEADLINE_UNITS),
        "deadline_n": S("integer", "e.g. 4 for the 4th business day after today."),
        "attempts": S("integer", "Persuasion attempts allowed."),
    })),
    "promise_date": O({
        "earliest": S("string", None, EARLIEST),
        "non_business": S("string", "What to offer when the customer names a weekend day or holiday inside the deadline.", NON_BUSINESS),
        "vague_ask_times": S("integer", "How many times to ask for the exact day after a vague period."),
    }),
    "amounts": O({
        "floor_offer_times": S("integer", "How many times the lower amount is offered when the full amount is too much."),
        "below_floor_offer_times": S("integer", "How many times the lower amount is offered when the customer proposes less."),
    }),
    "persuasion": O({"attempts": A(O({
        "n": S("integer", "1 for the first attempt."),
        "bands": A(S("string"), "Band names this attempt applies to; empty for all."),
        "amount": S("string", None, ATTEMPT_AMOUNTS),
        "date": S("string", None, NAMED_DATES),
        "if_today_is_that_date": S("string", "Date to use instead when today already is that date.", NAMED_DATES),
    }))}),
    "hardship": O({
        "enabled": S("boolean"),
        "trigger_examples": A(S("string")),
        "offer_transfer": S("boolean"),
        "transfer_queue": N("string", "Queue value of transfer_to_agent."),
    }),
    "requests": O({
        "already_paid": O({"enabled": S("boolean"), "trigger_examples": A(S("string"))}),
        "dispute": O({"enabled": S("boolean"), "trigger_examples": A(S("string"))}),
        "restructuring": O({"enabled": S("boolean"), "trigger_examples": A(S("string")), "queue": N("string")}),
        "human": O({"enabled": S("boolean"), "queue": N("string"), "ask_help_first_times": S("integer")}),
        "not_talking": O({"max_times": S("integer", "After how many 'I do not want to talk' the call closes. 0 if the brief has no such rule.")}),
    }),
    "promise": O({"retries": S("integer", "How many times a failed promise is tried again.")}),
    "outcomes": A(O({
        "situation": S("string", None, SITUATIONS),
        "outcome": S("string", "An outcome value of close_call."),
        "reason": N("string", "The reason value, or null where the table lists none."),
    }), "One row per situation."),
    "multi_product": O({
        "enabled": S("boolean", "The brief covers customers with several products."),
        "notes_enabled": S("boolean", "Products without a promise get a note."),
        "note_reasons": A(O({"situation": S("string", None, NOTE_SITUATIONS), "reason": S("string", "A reason value of add_note.")})),
        "clamp_to_deadline": S("boolean", "One date for everything that is after one product's deadline moves that product to its own deadline."),
    }),
    "tool_fields": A(O({"tool": S("string"), "role": S("string"), "field": S("string")}),
                     "For every tool role (see the instructions), the request field name the tool API uses."),
    "response_fields": A(O({"tool": S("string"), "role": S("string"), "field": S("string")}),
                         "For every response role, the response field name the tool API uses."),
    "tool_constants": A(O({"tool": S("string"), "field": S("string"), "value": S("string")}),
                        "Request fields that always get the same value, if the brief says so."),
    "custom_situations": A(O({
        "name": S("string", "A short snake_case name."),
        "trigger_examples": A(S("string"), "What the customer says that starts it."),
        "say_text": S("string", "What the agent says when it happens."),
        "verbatim": S("boolean", "true only if the brief gives the exact wording"),
        "outcome": N("string", "close_call outcome value when the call ends because of it; null when the call goes on."),
        "reason": N("string", "close_call reason value, or null."),
        "continue_for_promise": S("boolean", "true: say the text and carry on with the call (a promise can still be taken); false: the call ends."),
        "needs_callback": S("boolean", "true: ask when to call back and book a callback before closing."),
        "callback_ask_text": N("string", "The callback question, when needs_callback."),
        "applies_when": S("string", None, CUSTOM_WHEN),
    }), "Situations of the brief that no field above covers: a trigger, what to say, and how the call ends."),
    "unplaced_rules": A(O({"quote": S("string", "The rule, word for word from the brief."), "note": S("string")}),
                        "Only rules that no field above, including custom_situations, holds."),
})


# ---------------------------------------------------------------- normalize: never crash, fall back safely

def _int(x, default):
    try:
        return int(x)
    except Exception:
        return default


def normalize(spec, tools, warn):
    """Clamp the spec to the vocabularies and to the tool API. Unknown values fall back to the safest choice."""
    s = copy.deepcopy(spec) if isinstance(spec, dict) else {}

    def pick(obj, key, allowed, default, where):
        v = obj.get(key)
        if v not in allowed:
            warn(f"{where}.{key}: unknown value {v!r}, using {default!r}")
            obj[key] = default

    def enum_of(tool, field):
        return ((tools.get(tool) or {}).get("fields") or {}).get(field, {}).get("enum") or []

    s.setdefault("variables", {})
    s["variables"].setdefault("customer_id", "customer_id")
    s["variables"].setdefault("now", "now")
    s["variables"].setdefault("address_template", "{title} {last_name}")
    ph = s.setdefault("phrases", {})
    for k in PHRASES:
        if not isinstance(ph.get(k), dict) or not ph[k].get("text"):
            warn(f"phrases.{k} missing")
            ph[k] = {"text": "", "verbatim": False}

    s.setdefault("presence", {})["max_asks"] = max(1, _int(s["presence"].get("max_asks"), 2))
    tp = s.setdefault("third_party", {})
    pick(tp, "callback_days", CALLBACK_DAYS, "today_or_next_business_day", "third_party")
    for k, dflt in (("window_start", "00:00"), ("window_end", "23:59")):
        if not re.match(r"^\d{2}:\d{2}$", str(tp.get(k) or "")):
            warn(f"third_party.{k}: not HH:MM, using {dflt}")
            tp[k] = dflt
    tp["max_asks"] = max(1, _int(tp.get("max_asks"), 2))

    idn = s.setdefault("identity", {})
    fields_enum = enum_of("verify_identity", _role_field(s, "verify_identity", "field"))
    qs = []
    for q in idn.get("questions") or []:
        if not isinstance(q, dict):
            continue
        if fields_enum and q.get("field") not in fields_enum:
            warn(f"identity question field {q.get('field')!r} is not in the tool API {fields_enum}; dropped")
            continue
        pick(q, "answer_type", ANSWER_TYPES, "text", "identity.questions")
        pick(q, "numeric_date_order", DATE_ORDERS, "DMY", "identity.questions")
        qs.append(q)
    if not qs and fields_enum:
        warn("no usable identity questions; asking for every field the tool API offers")
        qs = [{"field": f, "ask_text": "", "answer_type": "text", "digits_length": None, "numeric_date_order": "DMY"} for f in fields_enum]
    idn["questions"] = qs
    idn["max_wrong_total"] = max(1, _int(idn.get("max_wrong_total"), 3))
    idn["max_refusals"] = max(1, _int(idn.get("max_refusals"), 2))
    hint_enum = (((tools.get("verify_identity") or {}).get("response") or {}).get(_resp_field(s, "verify_identity", "hint")) or {}).get("enum") or []
    for h in idn.get("hints") or []:
        if hint_enum and h.get("value") not in hint_enum:
            warn(f"hint {h.get('value')!r} is not in the tool API")

    c = s.setdefault("calendar", {})
    wd = [d for d in (c.get("business_weekdays") or []) if isinstance(d, int) and 0 <= d <= 6]
    if not wd:
        warn("calendar.business_weekdays empty, using Monday to Friday")
        wd = [0, 1, 2, 3, 4]
    c["business_weekdays"] = wd
    hol = []
    for h in c.get("holidays") or []:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", str(h)):
            hol.append(str(h))
        else:
            warn(f"holiday {h!r} is not YYYY-MM-DD; dropped")
    c["holidays"] = hol
    pick(c, "next_weekday", NEXT_WEEKDAY, "following_week", "calendar")
    pick(c, "numeric_date_order", DATE_ORDERS, "DMY", "calendar")

    type_enum = []
    acc = (tools.get("get_account") or {}).get("response") or {}
    prod_items = (acc.get(_resp_field(s, "get_account", "products")) or {}).get("items") or {}
    type_enum = (prod_items.get(_resp_field(s, "get_account", "type")) or {}).get("enum") or []
    prod_fields = list(prod_items)
    for p in s.get("products") or []:
        if type_enum and p.get("type") not in type_enum:
            warn(f"product type {p.get('type')!r} is not in the tool API")
        if prod_fields and p.get("floor_field") not in prod_fields:
            warn(f"floor_field {p.get('floor_field')!r} is not a get_account field; the full amount becomes the floor")
    bands = []
    for b in s.get("bands") or []:
        pick(b, "deadline_unit", DEADLINE_UNITS, "business_days", "bands")
        b["attempts"] = max(1, _int(b.get("attempts"), 1))
        bands.append(b)
    s["bands"] = sorted(bands, key=lambda b: _int(b.get("days_late_min"), 0))
    for a, b in zip(s["bands"], s["bands"][1:]):
        if _int(b.get("days_late_min"), 0) != _int(a.get("days_late_max"), 0) + 1:
            warn(f"bands {a.get('name')} and {b.get('name')} overlap or leave a gap")

    pd = s.setdefault("promise_date", {})
    pick(pd, "earliest", EARLIEST, "today", "promise_date")
    pick(pd, "non_business", NON_BUSINESS, "offer_next_business_day", "promise_date")
    for a in (s.setdefault("persuasion", {}).get("attempts") or []):
        pick(a, "amount", ATTEMPT_AMOUNTS, "full", "persuasion")
        pick(a, "date", NAMED_DATES, "deadline", "persuasion")
        pick(a, "if_today_is_that_date", NAMED_DATES, "deadline", "persuasion")

    queues = enum_of("transfer_to_agent", _role_field(s, "transfer_to_agent", "queue"))
    hs = s.setdefault("hardship", {})
    rq = s.setdefault("requests", {})
    for name, obj in (("hardship", hs), ("restructuring", rq.get("restructuring") or {}), ("human", rq.get("human") or {})):
        key = "transfer_queue" if name == "hardship" else "queue"
        if queues and obj.get(key) and obj.get(key) not in queues:
            warn(f"{name} queue {obj.get(key)!r} is not in the tool API; transfer switched off")
            obj[key] = None
            if name == "hardship":
                obj["offer_transfer"] = False

    outcomes_enum = enum_of("close_call", _role_field(s, "close_call", "outcome"))
    rows = []
    for o in s.get("outcomes") or []:
        if o.get("situation") not in SITUATIONS:
            warn(f"outcome row for unknown situation {o.get('situation')!r}; dropped")
            continue
        if outcomes_enum and o.get("outcome") not in outcomes_enum:
            warn(f"outcome {o.get('outcome')!r} is not in the tool API; dropped")
            continue
        rows.append(o)
    have = set(o["situation"] for o in rows)
    for sit in SITUATIONS:
        if sit not in have:
            warn(f"no outcome for situation {sit}")
    s["outcomes"] = rows

    mp = s.setdefault("multi_product", {})
    reasons = enum_of("add_note", _role_field(s, "add_note", "reason"))
    nr = []
    for r in mp.get("note_reasons") or []:
        if r.get("situation") not in NOTE_SITUATIONS or (reasons and r.get("reason") not in reasons):
            warn(f"note reason {r} not usable; dropped")
            continue
        nr.append(r)
    mp["note_reasons"] = nr
    if mp.get("notes_enabled") and "add_note" not in tools:
        warn("notes enabled but the tool API has no add_note; notes switched off")
        mp["notes_enabled"] = False

    for f in s.get("tool_fields") or []:
        flds = (tools.get(f.get("tool")) or {}).get("fields") or {}
        if flds and f.get("field") not in flds:
            warn(f"tool field {f} not in the tool API; using the role name")
            f["field"] = f.get("role")
    cs = []
    for c in s.get("custom_situations") or []:
        if not isinstance(c, dict) or not c.get("name") or not c.get("say_text"):
            warn(f"custom situation {c} incomplete; dropped")
            continue
        c["name"] = re.sub(r"[^a-z0-9_]", "_", str(c["name"]).lower())[:40]
        pick(c, "applies_when", CUSTOM_WHEN, "any", "custom_situations")
        if c.get("outcome") and outcomes_enum and c["outcome"] not in outcomes_enum:
            warn(f"custom situation {c['name']}: outcome {c['outcome']!r} not in the tool API; it goes on instead of closing")
            c["outcome"], c["continue_for_promise"] = None, True
        if not c.get("outcome") and not c.get("continue_for_promise"):
            warn(f"custom situation {c['name']}: ends the call but has no outcome; it goes on instead")
            c["continue_for_promise"] = True
        if c.get("needs_callback") and "schedule_callback" not in tools:
            c["needs_callback"] = False
        cs.append(c)
    s["custom_situations"] = cs
    s.setdefault("unplaced_rules", [])
    return s


def _role_field(s, tool, role):
    for f in s.get("tool_fields") or []:
        if f.get("tool") == tool and f.get("role") == role and f.get("field"):
            return f["field"]
    return role


def _resp_field(s, tool, role):
    for f in s.get("response_fields") or []:
        if f.get("tool") == tool and f.get("role") == role and f.get("field"):
            return f["field"]
    return role
