# The decision code that runs inside the workflow's code node ("brain").
#
# render.py embeds this whole file in the code node, followed by the spec and a call to brain(vars, spec).
# Rules for this file, because of the platform:
#   - only json, re and datetime may be imported
#   - two opening or two closing curly braces must never appear next to each other
#   - nothing may raise out of brain(); every path ends with next_step set
# Everything brief-specific comes from the spec S. This file only knows the builder's own vocabulary.
import json, re, datetime

D = datetime.date
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
MONTH_ABBR = dict((m[:3], i + 1) for i, m in enumerate(MONTHS))
MONTH_ABBR["sept"] = 9
UNITS = dict(zero=0, oh=0, o=0, nought=0, one=1, two=2, three=3, four=4, five=5, six=6, seven=7, eight=8, nine=9, ten=10,
             eleven=11, twelve=12, thirteen=13, fourteen=14, fifteen=15, sixteen=16, seventeen=17, eighteen=18, nineteen=19)
TENS = dict(twenty=20, thirty=30, forty=40, fifty=50, sixty=60, seventy=70, eighty=80, ninety=90)
ORD = dict(first=1, second=2, third=3, fourth=4, fifth=5, sixth=6, seventh=7, eighth=8, ninth=9, tenth=10, eleventh=11,
           twelfth=12, thirteenth=13, fourteenth=14, fifteenth=15, sixteenth=16, seventeenth=17, eighteenth=18,
           nineteenth=19, twentieth=20, thirtieth=30)
VAGUE_WORDS = ["next week", "end of the month", "end of month", "salary", "payday", "pay day", "paid", "later", "soon",
               "week after next", "some time", "sometime", "beginning of", "start of", "next month", "few days",
               "couple of days", "when i can", "not sure", "this month", "end of the week", "end of next week"]


# ---------------------------------------------------------------- small helpers

EMPTY = "none"
ENUM_VARS = ("presence", "q_kind", "id_reply", "reply", "applies_to_all")


def sval(V, k):
    v = V.get(k)
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    v = str(v).strip()
    return "" if (k in ENUM_VARS and v == EMPTY) else v


def consume(V, keys):
    # an enum variable only accepts its own values, so it is reset to EMPTY; text variables to ""
    for k in keys:
        V[k] = EMPTY if k in ENUM_VARS else ""


def jload(x, default):
    if isinstance(x, (dict, list)):
        return x
    try:
        return json.loads(x)
    except Exception:
        return default


def phrase(S, key, **kw):
    p = (S.get("phrases") or {}).get(key) or {}
    t = p.get("text") if isinstance(p, dict) else str(p)
    t = t or ""
    for k, v in kw.items():
        t = t.replace("<" + k + ">", str(v))
    return t.strip()


def fill_template(t, values):
    # replaces {name} with values[name]; unknown names stay as they are
    def rep(m):
        k = m.group(1)
        return str(values[k]) if k in values and values[k] not in (None, "") else m.group(0)
    return re.sub(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", rep, t or "")


def fmt_amount(x):
    try:
        x = float(x)
    except Exception:
        return str(x)
    if abs(x - round(x)) < 0.005:
        return "{:,}".format(int(round(x)))
    return "{:,.2f}".format(x)


def fmt_date(d, today=None):
    s = WEEKDAYS[d.weekday()].capitalize() + " " + str(d.day) + " " + MONTHS[d.month - 1].capitalize()
    if today is not None and d.year != today.year:
        s += " " + str(d.year)
    return s


def to_float(x):
    try:
        if x is None or x == "":
            return None
        if isinstance(x, (int, float)):
            return float(x)
        t = str(x).replace(",", "").strip()
        m = re.search(r"-?\d+(\.\d+)?", t)
        if m:
            return float(m.group(0))
        n = words_to_number(t)
        return float(n) if n is not None else None
    except Exception:
        return None


def words_to_number(text):
    # "four hundred and fifty-five point five" -> 455.5 ; returns None if no number words
    t = text.lower().replace("-", " ")
    toks = re.findall(r"[a-z]+|\d+(?:\.\d+)?", t)
    total, cur, seen, frac, in_frac = 0, 0, False, "", False
    for w in toks:
        if in_frac:
            if w in UNITS and UNITS[w] < 10:
                frac += str(UNITS[w]); continue
            if re.match(r"^\d+$", w):
                frac += w; continue
            break
        if re.match(r"^\d+(\.\d+)?$", w):
            cur += float(w); seen = True
        elif w in UNITS:
            cur += UNITS[w]; seen = True
        elif w in TENS:
            cur += TENS[w]; seen = True
        elif w == "hundred":
            cur = (cur or 1) * 100; seen = True
        elif w == "thousand":
            total += (cur or 1) * 1000; cur = 0; seen = True
        elif w in ("point", "dot") and seen:
            in_frac = True
        elif w in ("and", "a"):
            continue
        elif seen:
            break
    if not seen:
        return None
    v = total + cur
    if frac:
        v = float(str(int(v)) + "." + frac)
    return v


# ---------------------------------------------------------------- calendar

def cal(S):
    c = S.get("calendar") or {}
    wd = c.get("business_weekdays")
    if not isinstance(wd, list) or not wd:
        wd = [0, 1, 2, 3, 4]
    hol = set(str(h)[:10] for h in (c.get("holidays") or []))
    return wd, hol


def is_bday(S, d):
    wd, hol = cal(S)
    return d.weekday() in wd and d.isoformat() not in hol


def next_bday(S, d, include=True):
    x = d if include else d + datetime.timedelta(days=1)
    for _ in range(60):
        if is_bday(S, x):
            return x
        x += datetime.timedelta(days=1)
    return x


def prev_bday(S, d):
    x = d
    for _ in range(60):
        if is_bday(S, x):
            return x
        x -= datetime.timedelta(days=1)
    return x


def add_bdays(S, d, n):
    x, k = d, 0
    for _ in range(400):
        if k >= n:
            break
        x += datetime.timedelta(days=1)
        if is_bday(S, x):
            k += 1
    return x


def week_last_bday(S, d):
    # last business day of the Monday-Sunday week that contains d
    monday = d - datetime.timedelta(days=d.weekday())
    best = None
    for i in range(7):
        x = monday + datetime.timedelta(days=i)
        if is_bday(S, x):
            best = x
    return best


def parse_now(S, V):
    raw = sval(V, (S.get("variables") or {}).get("now") or "now")
    try:
        return datetime.datetime.fromisoformat(raw[:16])
    except Exception:
        try:
            return datetime.datetime.combine(D.fromisoformat(raw[:10]), datetime.time(12, 0))
        except Exception:
            return datetime.datetime(2000, 1, 3, 12, 0)


def resolve_named_date(S, kind, today, deadline):
    # builder vocabulary for dates the agent proposes
    if kind == "today":
        return today
    if kind == "tomorrow":
        return next_bday(S, today + datetime.timedelta(days=1))
    if kind == "end_of_this_week":
        d = week_last_bday(S, today)
        return d if d and d >= today else None
    if kind == "end_of_next_week":
        return week_last_bday(S, today + datetime.timedelta(days=7))
    if kind == "next_business_day":
        return next_bday(S, today, include=False)
    return deadline  # "deadline" and anything unknown


# ---------------------------------------------------------------- parsing what people say

def num_token(w):
    w = w.strip().lower()
    m = re.match(r"^(\d{1,2})(st|nd|rd|th)?$", w)
    if m:
        return int(m.group(1))
    if w in ORD:
        return ORD[w]
    if w in UNITS:
        return UNITS[w]
    return None


def day_numbers(t):
    # finds day-of-month numbers in digits or words, e.g. "26th", "twenty sixth", "the 3rd"
    out = []
    toks = re.findall(r"[a-z]+|\d+(?:st|nd|rd|th)?", t.replace("-", " "))
    i = 0
    while i < len(toks):
        w = toks[i]
        if w in TENS and i + 1 < len(toks) and (toks[i + 1] in ORD or toks[i + 1] in UNITS) and (ORD.get(toks[i + 1]) or UNITS.get(toks[i + 1]) or 0) < 10:
            out.append(TENS[w] + (ORD.get(toks[i + 1]) or UNITS.get(toks[i + 1]))); i += 2; continue
        n = num_token(w)
        if n is not None and 1 <= n <= 31 and (re.match(r"^\d", w) or w in ORD):
            out.append(n)
        elif w in TENS and TENS[w] in (20, 30) and (i + 1 >= len(toks) or toks[i + 1] not in UNITS):
            out.append(TENS[w])
        i += 1
    return out


def find_month(t):
    for w in re.findall(r"[a-z]+", t):
        if w in MONTHS:
            return MONTHS.index(w) + 1
        if w[:3] in MONTH_ABBR and len(w) <= 4 and w not in ("mar", "may", "jun") or w in ("sept",):
            return MONTH_ABBR.get(w[:4] if w == "sept" else w[:3])
    for w in re.findall(r"[a-z]+", t):
        if w in ("mar", "jun", "jul", "aug", "oct", "nov", "dec", "jan", "feb", "apr", "sep"):
            return MONTH_ABBR[w]
    return None


def parse_day_phrase(S, text, today):
    """A day the customer names, relative to today. Returns (date or None, 'date'|'vague'|'none')."""
    t = (text or "").lower().strip()
    if not t:
        return None, "none"
    t = re.sub(r"[,.!?]", " ", t)
    c = S.get("calendar") or {}
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        try:
            return D(int(m.group(1)), int(m.group(2)), int(m.group(3))), "date"
        except Exception:
            pass
    m = re.search(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        order = (S.get("calendar") or {}).get("numeric_date_order") or "DMY"
        day, mon = (b, a) if order == "MDY" else (a, b)
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100:
            y += 2000
        try:
            d = D(y, mon, day)
            if not m.group(3) and d < today:
                d = D(y + 1, mon, day)
            return d, "date"
        except Exception:
            pass
    if "day after tomorrow" in t:
        return today + datetime.timedelta(days=2), "date"
    if "tomorrow" in t:
        return today + datetime.timedelta(days=1), "date"
    if re.search(r"\b(today|tonight|this evening|this afternoon|right now|now)\b", t):
        return today, "date"
    mon = find_month(t)
    days = day_numbers(t)
    if mon and days:
        day = days[0]
        ym = re.search(r"\b(20\d\d)\b", t)
        y = int(ym.group(1)) if ym else today.year
        try:
            d = D(y, mon, day)
            if not ym and d < today:
                d = D(y + 1, mon, day)
            return d, "date"
        except Exception:
            return None, "none"
    wd = None
    for i, w in enumerate(WEEKDAYS):
        if re.search(r"\b" + w + r"\b", t):
            wd = i
    if days and not mon:
        # "the 26th" or "Monday the 26th": the next such day of a month, from today on
        day = days[0]
        y, mo = today.year, today.month
        for _ in range(3):
            try:
                d = D(y, mo, day)
                if d >= today:
                    return d, "date"
            except Exception:
                pass
            mo += 1
            if mo > 12:
                mo, y = 1, y + 1
        return None, "none"
    if wd is not None:
        monday = today - datetime.timedelta(days=today.weekday())
        if re.search(r"\bnext\s+" + WEEKDAYS[wd], t) or re.search(r"\b" + WEEKDAYS[wd] + r"\s+next\s+week", t):
            if c.get("next_weekday") == "next_occurrence":
                d = monday + datetime.timedelta(days=wd)
                return (d if d > today else d + datetime.timedelta(days=7)), "date"
            return monday + datetime.timedelta(days=7 + wd), "date"
        if re.search(r"\bthis\s+(coming\s+)?" + WEEKDAYS[wd], t):
            d = monday + datetime.timedelta(days=wd)
            return (d if d >= today else d + datetime.timedelta(days=7)), "date"
        d = monday + datetime.timedelta(days=wd)
        return (d if d >= today else d + datetime.timedelta(days=7)), "date"
    for w in VAGUE_WORDS:
        if w in t:
            return None, "vague"
    return None, "none"


def words_to_digits(text):
    # "four four seven one", "forty-four seventy-one", "double four seven one", "4 4 7 1" -> "4471"
    t = (text or "").lower().replace("-", " ")
    toks = re.findall(r"[a-z]+|\d+", t)
    out, rep, i = "", 1, 0
    while i < len(toks):
        w = toks[i]
        if w in ("double", "triple"):
            rep = 2 if w == "double" else 3; i += 1; continue
        if re.match(r"^\d+$", w):
            out += w * rep if len(w) == 1 else w
        elif w in TENS:
            v = TENS[w]
            if i + 1 < len(toks) and toks[i + 1] in UNITS and 0 < UNITS[toks[i + 1]] < 10:
                v += UNITS[toks[i + 1]]; i += 1
            out += str(v) * rep
        elif w in UNITS:
            out += str(UNITS[w]) * rep
        rep = 1
        i += 1
    return out


def parse_year_words(t):
    t = t.lower().replace("-", " ")
    m = re.search(r"\b(19\d\d|20\d\d)\b", t)
    if m:
        return int(m.group(1))
    toks = re.findall(r"[a-z]+", t)
    for i, w in enumerate(toks):
        if w in ("nineteen", "twenty") and i + 1 < len(toks):
            base = 1900 if w == "nineteen" else 2000
            rest = toks[i + 1:i + 3]
            if rest and rest[0] == "hundred":
                return base
            v = None
            if rest and rest[0] in TENS:
                v = TENS[rest[0]] + (UNITS[rest[1]] if len(rest) > 1 and rest[1] in UNITS and UNITS[rest[1]] < 10 else 0)
            elif rest and rest[0] in ("oh", "o") and len(rest) > 1 and rest[1] in UNITS:
                v = UNITS[rest[1]]
            elif rest and rest[0] in UNITS and UNITS[rest[0]] >= 10:
                v = UNITS[rest[0]]
            if v is not None:
                return base + v
        if w == "two" and i + 1 < len(toks) and toks[i + 1] == "thousand":
            rest = [x for x in toks[i + 2:i + 5] if x != "and"]
            v = 0
            if rest and rest[0] in TENS:
                v = TENS[rest[0]] + (UNITS[rest[1]] if len(rest) > 1 and rest[1] in UNITS and UNITS[rest[1]] < 10 else 0)
            elif rest and rest[0] in UNITS:
                v = UNITS[rest[0]]
            return 2000 + v
    return None


def parse_dob(text, order):
    """Returns ('ok', 'YYYY-MM-DD') or ('partial', None) or ('bad', None)."""
    t = (text or "").lower().strip()
    if not t:
        return "partial", None
    t2 = re.sub(r"[,]", " ", t)
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t2)
    if m:
        try:
            return "ok", D(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except Exception:
            return "bad", None
    m = re.search(r"\b(\d{1,4})[/.\- ](\d{1,2})[/.\- ](\d{2,4})\b", t2)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if order == "YMD" or a > 31:
            y, mo, d = a, b, c
        elif order == "MDY":
            mo, d, y = a, b, c
        else:
            d, mo, y = a, b, c
        if y < 100:
            y += 1900 if y > 30 else 2000
        try:
            return "ok", D(y, mo, d).isoformat()
        except Exception:
            return "bad", None
    mon = find_month(t2)
    year = parse_year_words(t2)
    t3 = re.sub(r"\b(19|20)\d\d\b", " ", t2)
    if year:
        # strip the year words so that "nineteen eighty-eight" does not look like a day
        t3 = re.sub(r"\b(nineteen|twenty|two thousand)(\s+(and\s+)?[a-z]+){0,2}\s*$", " ", t3)
    days = day_numbers(t3)
    if mon and days and year:
        try:
            return "ok", D(year, mon, days[0]).isoformat()
        except Exception:
            return "bad", None
    if mon or days or year:
        return "partial", None
    return "bad", None


def parse_time(text):
    """'around eleven', '11', '2 pm', 'half past ten', '14:30' -> 'HH:MM' or ''."""
    t = (text or "").lower().replace(".", ":")
    pm = bool(re.search(r"\b(pm|p m|afternoon|evening)\b", t))
    am = bool(re.search(r"\b(am|a m|morning)\b", t))
    m = re.search(r"\b(\d{1,2}):(\d{2})\b", t)
    h, mi = None, 0
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"\b(\d{1,2})\s*(?:o'?clock|am|pm|a m|p m)?\b", t)
        if m:
            h = int(m.group(1))
        else:
            half = re.search(r"half past ([a-z]+)", t)
            quarter = re.search(r"quarter past ([a-z]+)", t)
            for w in re.findall(r"[a-z]+", t):
                if w in UNITS and 1 <= UNITS[w] <= 12:
                    h = UNITS[w]; break
                if w == "noon" or w == "midday":
                    h = 12; break
            if half and half.group(1) in UNITS:
                h, mi = UNITS[half.group(1)], 30
            elif quarter and quarter.group(1) in UNITS:
                h, mi = UNITS[quarter.group(1)], 15
    if h is None:
        return ""
    if pm and h < 12:
        h += 12
    elif not am and 1 <= h <= 7:
        h += 12
    if h > 23 or mi > 59:
        return ""
    return "%02d:%02d" % (h, mi)


# ---------------------------------------------------------------- spec lookups

def outcome_for(S, situation):
    for o in S.get("outcomes") or []:
        if o.get("situation") == situation:
            return o.get("outcome") or "", o.get("reason") or ""
    return "", ""


def tool_field(S, tool, role):
    for f in S.get("tool_fields") or []:
        if f.get("tool") == tool and f.get("role") == role and f.get("field"):
            return f["field"]
    return role


def resp_field(S, tool, role):
    for f in S.get("response_fields") or []:
        if f.get("tool") == tool and f.get("role") == role and f.get("field"):
            return f["field"]
    return role


def band_for(S, days_late):
    bands = S.get("bands") or []
    for b in bands:
        try:
            if int(b.get("days_late_min")) <= days_late <= int(b.get("days_late_max")):
                return b
        except Exception:
            continue
    if bands:
        return sorted(bands, key=lambda b: int(b.get("attempts") or 0))[0]
    return {"name": "default", "deadline_unit": "business_days", "deadline_n": 5, "attempts": 1}


def compute_deadline(S, band, today):
    n = int(band.get("deadline_n") or 0)
    unit = band.get("deadline_unit") or "business_days"
    if unit == "calendar_days":
        return prev_bday(S, today + datetime.timedelta(days=n))
    if unit == "end_of_month":
        nm = D(today.year + (today.month // 12), today.month % 12 + 1, 1)
        return prev_bday(S, nm - datetime.timedelta(days=1))
    return add_bdays(S, today, n)


def queue_for(S, key):
    r = (S.get("requests") or {}).get(key) or {}
    if key == "hardship":
        r = S.get("hardship") or {}
        return r.get("transfer_queue") or ""
    return r.get("queue") or ""


# ---------------------------------------------------------------- the products after get_account

def products_from_result(S, data):
    lst = None
    key = resp_field(S, "get_account", "products")
    if isinstance(data, dict):
        lst = data.get(key)
        if lst is None:
            for v in data.values():
                if isinstance(v, list):
                    lst = v
                    break
    lst = jload(lst, []) if not isinstance(lst, list) else lst
    return [p for p in lst if isinstance(p, dict)]


def plan_products(S, raw, today):
    out = []
    types = dict((p.get("type"), p) for p in (S.get("products") or []) if isinstance(p, dict))
    f_id = resp_field(S, "get_account", "product_id")
    f_type = resp_field(S, "get_account", "type")
    f_due = resp_field(S, "get_account", "past_due")
    f_late = resp_field(S, "get_account", "days_late")
    for i, p in enumerate(raw):
        ptype = str(p.get(f_type) or "")
        tinfo = types.get(ptype) or {}
        due = to_float(p.get(f_due)) or 0.0
        late = int(to_float(p.get(f_late)) or 0)
        floor = to_float(p.get(tinfo.get("floor_field") or ""))
        if floor is None or floor <= 0 or floor > due:
            floor = due
        band = band_for(S, late)
        dl = compute_deadline(S, band, today)
        spoken = fill_template(tinfo.get("spoken_template") or ptype.replace("_", " "), p).strip() or ptype.replace("_", " ")
        out.append({"id": str(p.get(f_id) or ("p" + str(i + 1))), "spoken": spoken, "due": round(due, 2), "late": late,
                    "floor": round(floor, 2), "band": band.get("name") or "", "attempts": int(band.get("attempts") or 1),
                    "deadline": dl.isoformat(), "used": 0, "status": "open", "amount": None, "date": None,
                    "floor_offered": 0, "too_much": False, "vague": 0, "offer": None, "refused": [], "retries": 0,
                    "clamped": False, "below_offered": 0})
    return out


# ---------------------------------------------------------------- state

def load_state(V):
    st = jload(V.get("st"), None)
    return st if isinstance(st, dict) else None


def save(V, st):
    V["st"] = json.dumps(st)


def address(S, V):
    vals = dict((k, sval(V, k)) for k in ("title", "first_name", "last_name"))
    for k in list(V.keys()):
        if isinstance(k, str) and k not in vals and len(k) < 40:
            try:
                vals[k] = sval(V, k)
            except Exception:
                pass
    return fill_template((S.get("variables") or {}).get("address_template") or "{title} {last_name}", vals).strip()


def say_fixed(V, st, node, text):
    st["say"] = text
    V["say_line"] = text
    V["instruction"] = 'Say exactly: "' + text + '"'
    V["next_step"] = node + "_fixed"
    st["pending"] = node


def say_llm(V, st, node, instruction):
    V["instruction"] = instruction
    V["say_line"] = ""
    V["next_step"] = node + "_llm"
    st["pending"] = node


def call_tool(S, V, st, tool, values):
    # values: role -> value. Fields come from the spec mapping, so a renamed field still works.
    for role, val in values.items():
        V["a_" + tool + "_" + tool_field(S, tool, role)] = "" if val is None else str(val)
    V["res_" + tool] = ""
    V["next_step"] = "do_" + tool
    st["pending"] = "tool:" + tool


def tool_result(V, tool):
    raw = V.get("res_" + tool)
    d = jload(raw, None)
    return d if isinstance(d, dict) else None


def tool_ok(S, tool, d):
    if not isinstance(d, dict):
        return False
    k = resp_field(S, tool, "ok")
    v = d.get(k, True)
    return not (v is False or str(v).lower() == "false") and not d.get("error")


def warn(st, msg):
    st.setdefault("warnings", []).append(msg[:200])


# ---------------------------------------------------------------- closing

def set_final(S, V, st):
    """The outcome close_call sends. Updated on every run, so a call that ends early still closes sensibly."""
    sit = st.get("situation") or ""
    outcome, reason = "", ""
    prods = st.get("products") or []
    recorded = [p for p in prods if p.get("status") == "recorded"]
    if sit.startswith("transfer_"):
        outcome, reason = outcome_for(S, sit)
    elif recorded:
        outcome, reason = outcome_for(S, "promise_recorded")
    elif sit:
        outcome, reason = outcome_for(S, sit)
    elif prods:
        mp = S.get("multi_product") or {}
        notes = [p.get("note_sit") or p.get("status") for p in prods]
        if notes and all(n == "already_paid" for n in notes):
            outcome, reason = outcome_for(S, "already_paid")
        else:
            first = ""
            for p in prods:
                s = p.get("note_sit") or p.get("status")
                if s and s != "already_paid" and s not in ("open", "agreed"):
                    first = s
                    break
            outcome, reason = outcome_for(S, first or "refused")
    elif st.get("verified"):
        outcome, reason = outcome_for(S, "refused")
    elif st.get("phase") in ("identity",):
        outcome, reason = outcome_for(S, "id_declined")
    else:
        outcome, reason = outcome_for(S, "unclear")
    V["final_outcome"] = outcome
    V["final_reason"] = reason


def finish(S, V, st, situation, lead=""):
    if situation:
        st["situation"] = situation
    set_final(S, V, st)
    goodbye = phrase(S, "goodbye")
    text = (lead + " " + goodbye).strip() if goodbye and goodbye not in lead else lead.strip()
    V["farewell"] = text or goodbye or "Goodbye."
    V["next_step"] = "bye"
    st["pending"] = "bye"


# ---------------------------------------------------------------- phase: who is on the line

def ask_identity_question(S, V, st, prefix=""):
    q = phrase(S, "identity_question", address=address(S, V))
    q = fill_template(q, dict((k, sval(V, k)) for k in ("title", "first_name", "last_name")))
    say_fixed(V, st, "talk_pre", (prefix + " " + q).strip())


def answer_for_question(S, kind):
    if kind == "ai":
        return phrase(S, "ai_answer")
    if kind == "scam":
        return phrase(S, "scam_answer")
    if kind == "purpose":
        return ""
    if kind == "other":
        return phrase(S, "no_info")
    return ""


def handle_human_request(S, V, st, node_after):
    req = (S.get("requests") or {}).get("human") or {}
    if not req.get("enabled", True):
        return False
    st["human"] = int(st.get("human") or 0) + 1
    if st["human"] <= int(req.get("ask_help_first_times") or 0):
        say_llm(V, st, node_after, 'The customer asked for a person. Ask once, in one sentence, whether you can help them first: "' + phrase(S, "human_offer_help") + '". Do not transfer yet.')
        return True
    st["situation"] = "transfer_human"
    st["transfer_queue"] = queue_for(S, "human")
    call_tool(S, V, st, "transfer_to_agent", {"queue": st["transfer_queue"]})
    return True


def not_talking(S, V, st, node_after, verified):
    st["not_talking"] = int(st.get("not_talking") or 0) + 1
    mx = int(((S.get("requests") or {}).get("not_talking") or {}).get("max_times") or 2)
    if st["not_talking"] >= mx:
        if verified:
            for p in st.get("products") or []:
                if p.get("status") in ("open", "agreed"):
                    p["status"] = "refused"
            return "close_refused"
        return "close_declined"
    return "again"


def on_presence(S, V, st):
    kind = sval(V, "presence")
    q = sval(V, "q_kind")
    consume(V, ("presence", "q_kind"))
    pres = S.get("presence") or {}
    maxa = int(pres.get("max_asks") or 2)
    if kind == "deceased":
        return finish(S, V, st, "deceased", phrase(S, "condolence"))
    if kind == "wrong_number":
        return finish(S, V, st, "wrong_number", phrase(S, "wrong_number_ack"))
    if kind == "human":
        if handle_human_request(S, V, st, "talk_pre"):
            return
    if kind == "confirmed":
        st["phase"] = "identity"
        st["q_index"] = 0
        return ask_question(S, V, st)
    if kind == "other_person":
        st["phase"] = "third_party"
        st["cb_asks"] = 0
        return say_llm(V, st, "talk_pre", "The person on the line is not " + address(S, V) + ". Do not say why you are calling and say nothing about any account. " + phrase(S, "third_party_ask", address=address(S, V)))
    if kind == "not_talking":
        r = not_talking(S, V, st, "talk_pre", False)
        if r == "close_declined":
            return finish(S, V, st, "id_declined")
    st["asks"] = int(st.get("asks") or 1) + 1
    if st["asks"] > maxa:
        return finish(S, V, st, "unclear")
    ans = answer_for_question(S, q)
    ask_identity_question(S, V, st, ans)


def on_third_party(S, V, st, now):
    kind = sval(V, "presence")
    phrase_raw = sval(V, "cb_phrase")
    consume(V, ("presence", "cb_phrase", "q_kind"))
    tp = S.get("third_party") or {}
    if kind == "deceased":
        return finish(S, V, st, "deceased", phrase(S, "condolence"))
    if kind == "wrong_number":
        return finish(S, V, st, "wrong_number", phrase(S, "wrong_number_ack"))
    if kind == "confirmed":
        # the customer came to the phone
        st["phase"] = "identity"
        st["q_index"] = 0
        return ask_question(S, V, st)
    if not tp.get("callback_enabled", True):
        return finish(S, V, st, "no_callback")
    today = now.date()
    d, k = parse_day_phrase(S, phrase_raw, today)
    tm = parse_time(phrase_raw)
    if not phrase_raw or (d is None and not tm):
        if kind == "refuses" or kind == "not_talking":
            return finish(S, V, st, "no_callback")
        st["cb_vague"] = int(st.get("cb_vague") or 0) + 1
        if st["cb_vague"] > 2:
            return finish(S, V, st, "no_callback")
        return say_llm(V, st, "talk_pre", "Do not say why you are calling. Ask on which day and at what time " + address(S, V) + " can be reached.")
    if d is None:
        d = today
    if not tm:
        return say_llm(V, st, "talk_pre", "Do not say why you are calling. Ask at what time on " + fmt_date(d) + " " + address(S, V) + " can be reached.")
    ok = callback_ok(S, d, tm, now)
    if ok:
        st["cb"] = [d.isoformat(), tm]
        call_tool(S, V, st, "schedule_callback", {"date": d.isoformat(), "time": tm})
        return
    st["cb_asks"] = int(st.get("cb_asks") or 0) + 1
    if st["cb_asks"] >= int(tp.get("max_asks") or 2):
        return finish(S, V, st, "no_callback", phrase(S, "no_callback"))
    days = allowed_callback_days(S, now)
    window = (tp.get("window_start") or "") + " and " + (tp.get("window_end") or "")
    say_llm(V, st, "talk_pre", "That time is not possible. Do not say why you are calling. Ask once for another time: we can call back on " + " or ".join(fmt_date(x) for x in days) + ", between " + window + ".")


def allowed_callback_days(S, now):
    tp = S.get("third_party") or {}
    today = now.date()
    kind = tp.get("callback_days") or "today_or_next_business_day"
    n = int(tp.get("callback_days_n") or 1)
    if kind == "today_only":
        return [today]
    if kind == "next_business_day_only":
        return [next_bday(S, today, include=False)]
    if kind == "business_days_within_n":
        out, x = [], today
        for _ in range(n + 1):
            if is_bday(S, x):
                out.append(x)
            x += datetime.timedelta(days=1)
        return out or [next_bday(S, today, include=False)]
    return [today, next_bday(S, today, include=False)]


def callback_ok(S, d, tm, now):
    tp = S.get("third_party") or {}
    if d not in allowed_callback_days(S, now):
        return False
    start = tp.get("window_start") or "00:00"
    end = tp.get("window_end") or "23:59"
    if not (start <= tm <= end):
        return False
    if tp.get("after_now", True) and d == now.date() and tm <= now.strftime("%H:%M"):
        return False
    return True


# ---------------------------------------------------------------- phase: identity

def questions(S):
    qs = ((S.get("identity") or {}).get("questions")) or []
    return [q for q in qs if isinstance(q, dict) and q.get("field")]


def ask_question(S, V, st, prefix="", fixed=True):
    qs = questions(S)
    i = int(st.get("q_index") or 0)
    if i >= len(qs):
        return start_account(S, V, st)
    st["id_partial"] = ""
    text = (prefix + " " + (qs[i].get("ask_text") or "")).strip()
    if fixed:
        say_fixed(V, st, "talk_id", text)
    else:
        say_llm(V, st, "talk_id", 'Say: "' + text + '"')


def normalize_answer(q, raw, iso_hint):
    typ = q.get("answer_type") or "text"
    if typ == "date":
        status, val = parse_dob(raw, q.get("numeric_date_order") or "DMY")
        if status == "ok":
            return status, val
        if iso_hint and re.match(r"^\d{4}-\d{2}-\d{2}$", iso_hint) and status != "partial":
            return "ok", iso_hint
        if iso_hint and re.match(r"^\d{4}-\d{2}-\d{2}$", iso_hint) and status == "partial" and parse_year_words(raw):
            return "ok", iso_hint
        return status, None
    if typ == "digits":
        n = int(q.get("digits_length") or 0)
        dg = words_to_digits(raw)
        if not dg:
            return "partial", None
        if n and len(dg) < n:
            return "partial", None
        return "ok", dg[-n:] if n else dg
    if typ == "year":
        y = parse_year_words(raw)
        return ("ok", str(y)) if y else ("partial", None)
    v = raw.strip()
    return ("ok", v) if v else ("partial", None)


def on_identity_turn(S, V, st):
    raw = sval(V, "id_answer")
    iso = sval(V, "id_iso")
    rk = sval(V, "id_reply")
    q = sval(V, "q_kind")
    consume(V, ("id_answer", "id_iso", "id_reply", "q_kind"))
    idn = S.get("identity") or {}
    if rk == "human":
        if handle_human_request(S, V, st, "talk_id"):
            return
    if rk == "not_talking":
        if not_talking(S, V, st, "talk_id", False) == "close_declined":
            return finish(S, V, st, "id_declined")
        rk = "refuse"
    if rk == "asks_purpose" and idn.get("purpose_question_is_refusal", True):
        rk = "refuse"
    if rk == "refuse":
        st["refusals"] = int(st.get("refusals") or 0) + 1
        if st["refusals"] >= int(idn.get("max_refusals") or 2):
            return finish(S, V, st, "id_declined")
        return ask_question(S, V, st, phrase(S, "decline_explain"), fixed=True)
    if rk == "question" and not raw:
        ans = answer_for_question(S, q) or phrase(S, "no_info")
        return ask_question(S, V, st, ans, fixed=True)
    qs = questions(S)
    i = int(st.get("q_index") or 0)
    if i >= len(qs):
        return start_account(S, V, st)
    qd = qs[i]
    joined = ((st.get("id_partial") or "") + " " + raw).strip()
    status, val = normalize_answer(qd, joined, iso)
    if status == "ok":
        st["id_partial"] = ""
        st["id_last"] = val
        call_tool(S, V, st, "verify_identity", {"field": qd["field"], "answer": val})
        return
    if status == "partial" and raw:
        st["id_partial"] = joined
        return say_llm(V, st, "talk_id", "The customer gave only part of the answer. Ask them, in one short sentence, for the rest of it. Do not repeat the part they already gave.")
    st["id_partial"] = ""
    return ask_question(S, V, st, "", fixed=False)


def on_verify_result(S, V, st):
    d = tool_result(V, "verify_identity")
    idn = S.get("identity") or {}
    qs = questions(S)
    i = int(st.get("q_index") or 0)
    if d is None:
        st["verify_errors"] = int(st.get("verify_errors") or 0) + 1
        if st["verify_errors"] <= 2 and st.get("id_last"):
            call_tool(S, V, st, "verify_identity", {"field": qs[i]["field"], "answer": st["id_last"]})
            return
        return ask_question(S, V, st, "", fixed=False)
    hint = str(d.get(resp_field(S, "verify_identity", "hint")) or "")
    verified = str(d.get(resp_field(S, "verify_identity", "verified"))).lower() == "true"
    allv = str(d.get(resp_field(S, "verify_identity", "all_verified"))).lower() == "true"
    left = d.get(resp_field(S, "verify_identity", "wrong_answers_left"))
    if not tool_ok(S, "verify_identity", d) and not verified:
        # the service could not read the answer: not a wrong answer
        return say_llm(V, st, "talk_id", 'The answer could not be read. Ask again, in one sentence: "' + (qs[i].get("ask_text") or "") + '"')
    if allv or (verified and i + 1 >= len(qs)):
        st["verified"] = True
        return start_account(S, V, st)
    if verified:
        st["q_index"] = i + 1
        return ask_question(S, V, st, "", fixed=True)
    if hint:
        for h in idn.get("hints") or []:
            if h.get("value") == hint:
                if not h.get("counts_as_wrong", False):
                    return say_llm(V, st, "talk_id", h.get("instruction") or "Ask the customer to say it again.")
    st["wrong"] = int(st.get("wrong") or 0) + 1
    left_n = to_float(left)
    if (left_n is not None and left_n <= 0) or st["wrong"] >= int(idn.get("max_wrong_total") or 3):
        return finish(S, V, st, "id_failed", phrase(S, "id_failed"))
    return say_llm(V, st, "talk_id", 'That answer does not match. Do not say what the right answer is. Ask the same question again: "' + (qs[i].get("ask_text") or "") + '"')


# ---------------------------------------------------------------- phase: the account

def start_account(S, V, st):
    st["phase"] = "account"
    call_tool(S, V, st, "get_account", {})


def on_account_result(S, V, st, now):
    d = tool_result(V, "get_account")
    raw = products_from_result(S, d) if d is not None else []
    if not raw:
        st["account_errors"] = int(st.get("account_errors") or 0) + 1
        if st["account_errors"] <= 2:
            return start_account(S, V, st)
        return finish(S, V, st, "service_error", phrase(S, "service_error"))
    st["products"] = plan_products(S, raw, now.date())
    st["phase"] = "main"
    st["stage"] = "ask_today"
    st["cur"] = 0
    lines = [phrase(S, "debt_intro")]
    for p in st["products"]:
        lines.append(phrase(S, "debt_line", product=p["spoken"], amount=fmt_amount(p["due"]), days=p["late"]))
    multi = len(st["products"]) > 1
    lines.append(phrase(S, "pay_all_today" if multi else "pay_today"))
    say_fixed(V, st, "talk_main", " ".join(x for x in lines if x))


# ---------------------------------------------------------------- phase: getting the promise

def open_products(st):
    return [p for p in st.get("products") or [] if p.get("status") == "open"]


def current(st):
    ps = st.get("products") or []
    i = int(st.get("cur") or 0)
    while i < len(ps) and ps[i].get("status") != "open":
        i += 1
    st["cur"] = i
    return ps[i] if i < len(ps) else None


def offer_text(S, st, p, amount, date, today, extra=""):
    multi = len(st.get("products") or []) > 1
    what = (" for your " + p["spoken"]) if multi else ""
    a = fmt_amount(amount)
    when = "today" if date == today.isoformat() else "on " + fmt_date(D.fromisoformat(date), today)
    return (extra + " Can you pay " + a + what + " " + when + "?").strip()


def make_offer(S, V, st, p, amount, date, today, extra="", kind="offer"):
    p["offer"] = [round(float(amount), 2), date, kind]
    st["stage"] = "offer"
    say_llm(V, st, "talk_main", 'Say, in your own words but with exactly these figures: "' + offer_text(S, st, p, amount, date, today, extra) + '" Do not offer anything else.')


def attempt_offer(S, V, st, p, today):
    """A flat refusal: use the next persuasion attempt, or stop."""
    attempts = [a for a in ((S.get("persuasion") or {}).get("attempts") or []) if isinstance(a, dict)]
    attempts.sort(key=lambda a: int(a.get("n") or 0))
    dl = D.fromisoformat(p["deadline"])
    while int(p.get("used") or 0) < int(p.get("attempts") or 1):
        n = int(p.get("used") or 0) + 1
        p["used"] = n
        spec = None
        for a in attempts:
            if int(a.get("n") or 0) == n and (not a.get("bands") or p.get("band") in a.get("bands")):
                spec = a
                break
        if spec is None:
            continue
        kind = spec.get("amount") or "full"
        amount = p["floor"] if kind == "floor" or (kind == "full_or_floor_if_too_much" and p.get("too_much")) else p["due"]
        d = resolve_named_date(S, spec.get("date") or "deadline", today, dl)
        if d is None or (d == today and spec.get("date") == "end_of_this_week"):
            d = resolve_named_date(S, spec.get("if_today_is_that_date") or "end_of_next_week", today, dl)
        if d is None or d > dl:
            d = dl
        if d < today:
            d = today
        key = [round(float(amount), 2), d.isoformat()]
        if key in [r[:2] for r in p.get("refused") or []]:
            continue
        return make_offer(S, V, st, p, amount, d.isoformat(), today, kind="attempt")
    p["status"] = "refused"
    return next_product(S, V, st, today)


def check_date(S, p, d, today):
    """Returns (ok_date_or_None, problem) for a day the customer named."""
    dl = D.fromisoformat(p["deadline"])
    earliest = today if ((S.get("promise_date") or {}).get("earliest") or "today") == "today" else today + datetime.timedelta(days=1)
    if d < earliest:
        return None, "past"
    if d > dl:
        return dl, "after_deadline"
    if not is_bday(S, d):
        nb = next_bday(S, d)
        if nb > dl:
            return prev_bday(S, dl), "non_business"
        return nb, "non_business"
    return d, ""


def check_amount(S, p, a):
    if a is None:
        return None, ""
    if a > p["due"] + 0.005:
        return p["due"], "over"
    if a + 0.005 < p["floor"]:
        return p["floor"], "below"
    return round(a, 2), ""


def agree(S, V, st, p, amount, date, today):
    p["amount"] = round(float(amount), 2)
    p["date"] = date
    p["status"] = "agreed"
    p["offer"] = None
    return next_product(S, V, st, today)


def next_product(S, V, st, today):
    p = current(st)
    if p is not None:
        if p.get("entered"):
            return attempt_offer(S, V, st, p, today) if p.get("needs_attempt") else ask_for_product(S, V, st, p, today)
        p["entered"] = True
        return attempt_offer(S, V, st, p, today)
    return readback(S, V, st, today)


def ask_for_product(S, V, st, p, today):
    p["needs_attempt"] = False
    return attempt_offer(S, V, st, p, today)


def readback(S, V, st, today):
    agreed = [p for p in st.get("products") or [] if p.get("status") == "agreed"]
    if not agreed:
        return after_records(S, V, st, today)
    parts = []
    multi = len(st.get("products") or []) > 1
    for p in agreed:
        when = "today" if p["date"] == today.isoformat() else "on " + fmt_date(D.fromisoformat(p["date"]), today)
        s = fmt_amount(p["amount"]) + " for your " + p["spoken"] + " " + when
        if p.get("clamped"):
            s += " (" + phrase(S, "clamp_note", product=p["spoken"], date=fmt_date(D.fromisoformat(p["date"]), today)) + ")"
        parts.append(s)
    text = "So that is " + ("; ".join(parts[:-1]) + " and " + parts[-1] if len(parts) > 1 else parts[0]) + ". " + phrase(S, "confirm_question")
    st["stage"] = "confirm"
    say_fixed(V, st, "talk_main", text)


def record_next(S, V, st, today):
    for p in st.get("products") or []:
        if p.get("status") == "confirmed":
            call_tool(S, V, st, "create_promise", {"product_id": p["id"], "amount": p["amount"], "date": p["date"]})
            st["recording"] = p["id"]
            return
    return after_records(S, V, st, today)


def on_promise_result(S, V, st, today):
    d = tool_result(V, "create_promise")
    pid = st.get("recording")
    p = None
    for x in st.get("products") or []:
        if x.get("id") == pid:
            p = x
    if p is None:
        return after_records(S, V, st, today)
    if tool_ok(S, "create_promise", d):
        p["status"] = "recorded"
        return record_next(S, V, st, today)
    p["retries"] = int(p.get("retries") or 0) + 1
    if p["retries"] <= int((S.get("promise") or {}).get("retries") or 1):
        call_tool(S, V, st, "create_promise", {"product_id": p["id"], "amount": p["amount"], "date": p["date"]})
        return
    p["status"] = "failed"
    p["note_sit"] = "service_error"
    return record_next(S, V, st, today)


def notes_enabled(S):
    mp = S.get("multi_product") or {}
    return bool(mp.get("enabled")) and bool(mp.get("notes_enabled"))


def note_reason(S, sit):
    for r in (S.get("multi_product") or {}).get("note_reasons") or []:
        if r.get("situation") == sit:
            return r.get("reason") or ""
    return ""


def after_records(S, V, st, today):
    # notes for every product without a promise, then the goodbye
    if notes_enabled(S) and not str(st.get("situation") or "").startswith("transfer_"):
        for p in st.get("products") or []:
            if p.get("status") in ("recorded",) or p.get("noted"):
                continue
            sit = p.get("note_sit") or ({"refused": "refused", "open": "refused", "agreed": "refused", "confirmed": "refused"}.get(p.get("status")) or p.get("status"))
            reason = note_reason(S, sit)
            p["noted"] = True
            if not reason:
                warn(st, "no note reason for " + str(sit))
                continue
            p["note_sit"] = sit
            call_tool(S, V, st, "add_note", {"product_id": p["id"], "reason": reason, "text": sit})
            return
    return closing_words(S, V, st, today)


def closing_words(S, V, st, today):
    prods = st.get("products") or []
    rec = [p for p in prods if p.get("status") == "recorded"]
    failed = [p for p in prods if p.get("status") == "failed"]
    lines = []
    if rec:
        parts = []
        for p in rec:
            when = "today" if p["date"] == today.isoformat() else "on " + fmt_date(D.fromisoformat(p["date"]), today)
            parts.append(fmt_amount(p["amount"]) + " for your " + p["spoken"] + " " + when)
        lines.append("Your payment promise of " + " and ".join(parts) + " is recorded.")
        lines.append(phrase(S, "after_promise"))
    if failed:
        lines.append(phrase(S, "service_error", product=", ".join(p["spoken"] for p in failed)))
    if not rec and not failed:
        sit = st.get("situation") or ""
        if sit == "already_paid" or (prods and all((p.get("note_sit") or p.get("status")) == "already_paid" for p in prods)):
            pass
    return finish(S, V, st, st.get("situation") or "", " ".join(x for x in lines if x))


def apply_date_to_all(S, V, st, d, amount, today, p0):
    """One date for everything that is still open (multi product): each product on its own deadline."""
    targets = [p for p in st.get("products") or [] if p.get("status") == "open"]
    if p0 not in targets:
        targets = [p0] + targets
    for p in targets:
        ok_d, problem = check_date(S, p, d, today)
        if ok_d is None:
            return None
        p["clamped"] = problem == "after_deadline"
        p["amount"] = round(float(amount if (amount is not None and p is p0) else p["due"]), 2)
        p["date"] = ok_d.isoformat()
        p["status"] = "agreed"
        p["offer"] = None
    return True


def on_main_turn(S, V, st, now):
    today = now.date()
    reply = sval(V, "reply")
    dphrase = sval(V, "date_phrase")
    amount = to_float(V.get("amount"))
    allp = sval(V, "applies_to_all")
    q = sval(V, "q_kind")
    consume(V, ("reply", "date_phrase", "amount", "applies_to_all", "q_kind"))
    stage = st.get("stage") or "ask_today"
    prods = st.get("products") or []
    multi = len(prods) > 1
    mp = S.get("multi_product") or {}
    p = current(st)

    # requests that end or redirect the call come first
    if reply == "restructuring" and ((S.get("requests") or {}).get("restructuring") or {}).get("enabled", True):
        for x in prods:
            if x.get("status") in ("agreed", "confirmed"):
                x["status"] = "open"
        st["situation"] = "transfer_restructuring"
        st["transfer_queue"] = queue_for(S, "restructuring")
        return call_tool(S, V, st, "transfer_to_agent", {"queue": st["transfer_queue"]})
    if reply == "human":
        if handle_human_request(S, V, st, "talk_main"):
            return
    if stage == "hardship_offer":
        if reply in ("yes", "accept"):
            st["situation"] = "transfer_support"
            st["transfer_queue"] = queue_for(S, "hardship")
            return call_tool(S, V, st, "transfer_to_agent", {"queue": st["transfer_queue"]})
        if reply in ("no", "refuse", "not_talking") and not dphrase and amount is None:
            for x in prods:
                if x.get("status") == "open":
                    x["status"] = "hardship"
                    x["note_sit"] = "hardship"
            if not multi:
                st["situation"] = "hardship"
            return readback(S, V, st, today)
    if reply == "hardship" and (S.get("hardship") or {}).get("enabled", True) and not st.get("hardship_done"):
        st["hardship_done"] = True
        hs = S.get("hardship") or {}
        if hs.get("offer_transfer", True) and queue_for(S, "hardship"):
            st["stage"] = "hardship_offer"
            return say_llm(V, st, "talk_main", 'Say exactly one short sentence of sympathy: "' + phrase(S, "hardship_sympathy") + '" Then offer: "' + phrase(S, "hardship_offer_transfer") + '" Do not ask for any payment.')
        for x in prods:
            if x.get("status") == "open":
                x["status"] = "hardship"
                x["note_sit"] = "hardship"
        if not multi:
            st["situation"] = "hardship"
        return readback(S, V, st, today)
    if reply == "already_paid" and ((S.get("requests") or {}).get("already_paid") or {}).get("enabled", True):
        target = p if (multi and p is not None and stage != "ask_today") else None
        if multi and target is not None:
            target["status"] = "already_paid"
            target["note_sit"] = "already_paid"
            say_line = phrase(S, "already_paid")
            nxt = current(st)
            if nxt is None:
                return readback(S, V, st, today) if any(x.get("status") == "agreed" for x in prods) else after_records_with(S, V, st, today, say_line)
            return attempt_with_lead(S, V, st, nxt, today, say_line)
        for x in prods:
            if x.get("status") == "open":
                x["status"] = "already_paid"
                x["note_sit"] = "already_paid"
        if not multi:
            st["situation"] = "already_paid"
        return after_records_with(S, V, st, today, phrase(S, "already_paid"))
    if reply == "dispute" and ((S.get("requests") or {}).get("dispute") or {}).get("enabled", True):
        if multi and p is not None and stage != "ask_today":
            p["status"] = "dispute"
            p["note_sit"] = "dispute"
            nxt = current(st)
            lead = phrase(S, "dispute_ack")
            if nxt is None:
                return readback(S, V, st, today) if any(x.get("status") == "agreed" for x in prods) else after_records_with(S, V, st, today, lead)
            return attempt_with_lead(S, V, st, nxt, today, lead)
        for x in prods:
            if x.get("status") == "open":
                x["status"] = "dispute"
                x["note_sit"] = "dispute"
        if not multi:
            st["situation"] = "dispute"
        return after_records_with(S, V, st, today, phrase(S, "dispute_ack"))
    if reply == "not_talking":
        if not_talking(S, V, st, "talk_main", True) == "close_refused":
            if not multi:
                st["situation"] = "refused"
            return readback(S, V, st, today)
        return say_llm(V, st, "talk_main", "The customer does not want to talk. Acknowledge it in one sentence and repeat the last question once.")
    if reply == "change_recorded":
        return say_llm(V, st, "talk_main", 'Say: "' + phrase(S, "changes_after_record") + '" Then continue with the last question.')

    # the read-back
    if stage == "confirm":
        if reply in ("yes", "accept") and not dphrase and amount is None:
            for x in prods:
                if x.get("status") == "agreed":
                    x["status"] = "confirmed"
            return record_next(S, V, st, today)
        if dphrase or amount is not None:
            agreed = [x for x in prods if x.get("status") == "agreed"]
            target = agreed[-1] if agreed else None
            if target is not None:
                target["status"] = "open"
                p = target
                st["cur"] = prods.index(target)
                stage = "offer"
                target["offer"] = [target["amount"], target["date"], "readback"]
        else:
            # not a clear yes: treat it as a refusal of what was read back
            agreed = [x for x in prods if x.get("status") == "agreed"]
            for x in agreed:
                x["status"] = "open"
                x["refused"] = (x.get("refused") or []) + [[x["amount"], x["date"]]]
            p = current(st)
            if p is None:
                return readback(S, V, st, today)
            return attempt_offer(S, V, st, p, today)

    if p is None:
        return readback(S, V, st, today)

    # a date or an amount from the customer is never a refusal
    d, dkind = parse_day_phrase(S, dphrase, today) if dphrase else (None, "none")
    if dkind == "vague" or reply == "vague":
        if d is None:
            p["vague"] = int(p.get("vague") or 0) + 1
            if p["vague"] <= int((S.get("promise_date") or {}).get("vague_ask_times") or 1):
                return say_llm(V, st, "talk_main", "The customer named no exact day. Ask once for the exact day they can pay" + ((" for the " + p["spoken"]) if multi else "") + ". Do not suggest a day yourself.")
            dl = D.fromisoformat(p["deadline"])
            amt = p["offer"][0] if p.get("offer") else (p["floor"] if p.get("too_much") else p["due"])
            return make_offer(S, V, st, p, amt, dl.isoformat(), today, kind="deadline")
    if reply == "too_much" and amount is None and d is None:
        p["too_much"] = True
        if int(p.get("floor_offered") or 0) < int((S.get("amounts") or {}).get("floor_offer_times") or 1) and p["floor"] < p["due"]:
            p["floor_offered"] = int(p.get("floor_offered") or 0) + 1
            date = (p.get("offer") or [None, today.isoformat()])[1]
            return make_offer(S, V, st, p, p["floor"], date, today, extra=phrase(S, "floor_caveat", amount=fmt_amount(p["floor"])), kind="floor")
        reply = "refuse"
    if d is not None or amount is not None:
        base_amt = p["offer"][0] if p.get("offer") else (p["floor"] if p.get("too_much") else p["due"])
        base_date = p["offer"][1] if p.get("offer") else None
        if stage == "ask_today" and base_date is None and reply in ("yes", "accept"):
            base_date = today.isoformat()
        a, aprob = check_amount(S, p, amount) if amount is not None else (base_amt, "")
        if aprob == "below":
            if int(p.get("below_offered") or 0) < int((S.get("amounts") or {}).get("below_floor_offer_times") or 1):
                p["below_offered"] = int(p.get("below_offered") or 0) + 1
                date = d.isoformat() if d is not None else (base_date or today.isoformat())
                if d is not None:
                    ok_d, _ = check_date(S, p, d, today)
                    date = (ok_d or today).isoformat()
                return make_offer(S, V, st, p, p["floor"], date, today, extra="That amount cannot be recorded. The lowest amount I can record is " + fmt_amount(p["floor"]) + ".", kind="floor")
            return refusal(S, V, st, p, today)
        if d is None:
            if base_date is None:
                p["offer"] = [a, None, "amount"]
                return say_llm(V, st, "talk_main", "Ask on which day the customer can pay " + fmt_amount(a) + ((" for the " + p["spoken"]) if multi else "") + ". Do not suggest a day yourself.")
            d = D.fromisoformat(base_date)
        ok_d, problem = check_date(S, p, d, today)
        if ok_d is None:
            return say_llm(V, st, "talk_main", "That day is in the past. Ask for a day from today on.")
        if multi and (allp == "yes" or stage == "ask_today") and mp.get("clamp_to_deadline", True) and len(open_products(st)) > 1:
            if apply_date_to_all(S, V, st, d, amount if amount is not None else None, today, p):
                return readback(S, V, st, today)
        if problem == "after_deadline":
            return make_offer(S, V, st, p, a, ok_d.isoformat(), today, extra="The latest date I can record is " + fmt_date(ok_d, today) + ".", kind="deadline")
        if problem == "non_business":
            return make_offer(S, V, st, p, a, ok_d.isoformat(), today, extra=fmt_date(d, today) + " is not a business day. The next business day is " + fmt_date(ok_d, today) + ".", kind="next_bday")
        return agree(S, V, st, p, a, ok_d.isoformat(), today)
    if reply in ("yes", "accept"):
        if stage == "ask_today":
            if multi:
                for x in open_products(st):
                    x["amount"], x["date"], x["status"] = x["due"], today.isoformat(), "agreed"
                return readback(S, V, st, today)
            return agree(S, V, st, p, p["due"], today.isoformat(), today)
        if p.get("offer") and p["offer"][1]:
            return agree(S, V, st, p, p["offer"][0], p["offer"][1], today)
        return agree(S, V, st, p, p["due"], today.isoformat(), today)
    if reply in ("no", "refuse"):
        return refusal(S, V, st, p, today)
    if reply == "question" or q:
        ans = answer_for_question(S, q) or phrase(S, "no_info")
        return say_llm(V, st, "talk_main", 'Answer the customer in one sentence: "' + ans + '" Then repeat the last question, with the same figures.')
    return say_llm(V, st, "talk_main", "Reply briefly to what the customer said, without new figures or offers, then repeat the last question with the same figures.")


def refusal(S, V, st, p, today):
    if p.get("offer"):
        p["refused"] = (p.get("refused") or []) + [p["offer"][:2]]
    if st.get("stage") == "ask_today":
        multi = len(st.get("products") or []) > 1
        st["stage"] = "offer"
        if multi:
            for x in open_products(st):
                x["entered"] = False
            p = current(st)
            p["entered"] = True
        return attempt_offer(S, V, st, p, today)
    return attempt_offer(S, V, st, p, today)


def attempt_with_lead(S, V, st, p, today, lead):
    p["entered"] = True
    attempt_offer(S, V, st, p, today)
    if V.get("next_step") == "talk_main_llm":
        V["instruction"] = 'First say: "' + lead + '" ' + V["instruction"]
    return


def after_records_with(S, V, st, today, lead):
    st["lead"] = lead
    return after_records(S, V, st, today)


# ---------------------------------------------------------------- entry point

def brain(V, S):
    try:
        run(V, S)
    except Exception as e:
        try:
            st = load_state(V) or {}
            warn(st, "brain error: " + repr(e))
            save(V, st)
        except Exception:
            pass
        V["instruction"] = "Apologise briefly and repeat your last question."
        V["next_step"] = "talk_main_llm" if (load_state(V) or {}).get("phase") == "main" else "talk_pre_llm"


def run(V, S):
    now = parse_now(S, V)
    st = load_state(V)
    if st is None:
        st = {"phase": "presence", "asks": 1, "pending": ""}
        set_final(S, V, st)
        V["farewell"] = phrase(S, "goodbye") or "Goodbye."
        ask_identity_question(S, V, st, phrase(S, "opening"))
        save(V, st)
        return
    pend = st.get("pending") or ""
    phase = st.get("phase")
    if pend == "tool:verify_identity":
        on_verify_result(S, V, st)
    elif pend == "tool:get_account":
        on_account_result(S, V, st, now)
    elif pend == "tool:create_promise":
        on_promise_result(S, V, st, now.date())
    elif pend == "tool:add_note":
        after_records(S, V, st, now.date())
    elif pend == "tool:schedule_callback":
        d = tool_result(V, "schedule_callback")
        if tool_ok(S, "schedule_callback", d):
            finish(S, V, st, "callback", phrase(S, "callback_confirm", date=fmt_date(D.fromisoformat(st["cb"][0]), now.date()), time=st["cb"][1]))
        else:
            st["cb_fail"] = int(st.get("cb_fail") or 0) + 1
            if st["cb_fail"] <= 1:
                call_tool(S, V, st, "schedule_callback", {"date": st["cb"][0], "time": st["cb"][1]})
            else:
                finish(S, V, st, "no_callback", phrase(S, "service_error", product="callback"))
    elif pend == "tool:transfer_to_agent":
        finish(S, V, st, st.get("situation") or "", phrase(S, "transfer_announce"))
    elif phase == "presence":
        on_presence(S, V, st)
    elif phase == "third_party":
        on_third_party(S, V, st, now)
    elif phase == "identity":
        on_identity_turn(S, V, st)
    elif phase == "main":
        on_main_turn(S, V, st, now)
    else:
        finish(S, V, st, "")
    if st.get("lead") and V.get("next_step") == "bye":
        V["farewell"] = (st.pop("lead") + " " + V.get("farewell", "")).strip()
    set_final(S, V, st)
    save(V, st)
