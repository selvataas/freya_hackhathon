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
ENUM_VARS = ("presence", "q_kind", "id_reply", "reply", "applies_to_all", "custom", "message_state")
# the builder's own words, not a brief's: said while waiting for the rest of a cut-off message, and after a failed save
GO_ON = "Go on."
RETRIED_OK = "That didn't go through the first time, but I've tried again and it is now recorded."
ONE_AT_A_TIME = "Let's take them one at a time."
# ways to say the builder's own lines, used in turn so that a call does not open several replies the same way
VARIANTS = {
    "go_on": ["Go on.", "Please, go on.", "I'm listening.", "Take your time."],
    "sorry": ["Sorry about that.", "My apologies.", "Sorry, my mistake."],
    "yes_no": ["A yes or a no is enough.", "Just a yes or a no, please.", "A simple yes or no is fine."],
    "not_understood": ["Sorry, I missed that.", "I'm sorry, I didn't get that.", "Sorry, could you say that again?"],
    "date": ["Just the date, please: the day, the month and the year.", "Could you say the full date: day, month and year?", "The day, the month and the year, please."],
    "digits": ["Just the <n> digits, please, one by one.", "Could you read me the <n> digits, one at a time?", "The <n> digits, please, slowly."],
    "digits_any": ["Just the digits, please, one by one.", "Could you read me the digits, one at a time?"],
    "year_only": ["Just the year, please.", "Could you tell me the year, please?", "Which year, please?"],
    "month_only": ["Just the month, please.", "Which month, please?"],
    "day_only": ["Just the day, please.", "Which day of the month, please?"],
    "rest_digits": ["Just the remaining <k> digits, please.", "And the last <k> digits?", "Could you give me the other <k> digits?"],
    "rest": ["Just the rest of it, please.", "And the rest, please?"],
}


def variant(st, key, **kw):
    """The next way of saying one of the builder's lines in this call."""
    opts = VARIANTS[key]
    used = st.setdefault("variants", {})
    i = int(used.get(key) or 0)
    used[key] = i + 1
    t = opts[i % len(opts)]
    for k, v in kw.items():
        t = t.replace("<" + k + ">", str(v))
    return t


def not_understood(S, st):
    """The spec's line first; when it is not the brief's exact words, it takes turns with the builder's own."""
    p = (S.get("phrases") or {}).get("not_understood") or {}
    n = int(st.get("nu_count") or 0)
    st["nu_count"] = n + 1
    if p.get("verbatim") or n % 2 == 0 or not p.get("text"):
        return phrase(S, "not_understood")
    return variant(st, "not_understood")
NOT_SAVED_FINAL = "Just to be clear, this has not been saved."


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


TRUE_WORDS = ("true", "yes", "y", "1", "ok", "verified", "passed")
FALSE_WORDS = ("false", "no", "n", "0", "failed", "none", "null")


def truthy(v):
    """A boolean from an API as it may come: True, 'true', 'True', 'yes', 1."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() in TRUE_WORDS


def falsy(v):
    if isinstance(v, bool):
        return not v
    if isinstance(v, (int, float)):
        return v == 0
    return str(v).strip().lower() in FALSE_WORDS


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
    t = re.sub(r"\s{2,}", " ", t)
    return re.sub(r"\s+([.,;:?!])", r"\1", t).strip()


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


def day_numbers(t, cardinals=False):
    # day-of-month numbers in digits or words: "26th", "twenty sixth", "the 3rd"; with cardinals also "fourteen"
    out = []
    toks = re.findall(r"[a-z]+|\d+(?:st|nd|rd|th)?", t.replace("-", " "))
    i = 0
    while i < len(toks):
        w = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        unit = ORD.get(nxt) or (UNITS.get(nxt) if cardinals or nxt in ORD else None)
        if w in TENS and TENS[w] in (20, 30) and unit is not None and 0 < unit < 10:
            out.append(TENS[w] + unit); i += 2; continue
        n = num_token(w)
        if n is not None and 1 <= n <= 31 and (re.match(r"^\d", w) or w in ORD or (cardinals and w in UNITS)):
            out.append(n)
        elif w in TENS and TENS[w] in (20, 30) and (cardinals or w == "thirtieth"):
            out.append(TENS[w])
        elif w in ("twentieth", "thirtieth"):
            out.append(ORD[w])
        i += 1
    return out


MONTH_SHORT = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}


def find_month(t):
    toks = re.findall(r"[a-z]+|\d+", t)
    for i, w in enumerate(toks):
        if w == "may":
            # "may" is a month only next to a number: "3 May", "May 3rd", "may the 3rd"
            near = toks[max(0, i - 2):i] + toks[i + 1:i + 3]
            if any(re.match(r"^\d", x) or x in ORD or x in UNITS or x in TENS for x in near):
                return 5
            continue
        if w in MONTHS:
            return MONTHS.index(w) + 1
        if w in MONTH_SHORT:
            return MONTH_SHORT[w]
    return None


# "the 21st, sorry, I mean the 20th": words that start a correction of what was just said
CORRECTION = re.compile(r"\b(?:sorry|i mean|i meant|actually|no wait|rather|correction)\b", re.I)


def corrected(text, parse):
    """What a message names, after its corrections. parse(part) returns a dict of what one part names; later parts
    replace only what they name: 'tomorrow at 11, sorry, I mean 12' keeps tomorrow and takes 12."""
    parts = CORRECTION.split(text or "")
    if len(parts) == 1:
        parts = [text or ""]
    out = {}
    for part in parts:
        if part.strip(" ,.;:!?-"):
            out.update((k, v) for k, v in (parse(part) or {}).items() if v not in (None, ""))
    return out


def parse_day_phrase(S, text, today):
    """A day the customer names, relative to today. Returns (date or None, 'date'|'vague'|'none')."""
    t = (text or "").lower().strip()
    if not t:
        return None, "none"
    # "the 21st, sorry, I mean the 20th": the part after the last correction counts
    parts = CORRECTION.split(t)
    if len(parts) > 1 and parts[-1].strip(" ,.!?"):
        t = parts[-1]
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
    days = day_numbers(t, cardinals=bool(mon))
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
        if re.search(r"\bthis\s+" + WEEKDAYS[wd], t):
            # the one in the current week, even if it has passed: the date check then says so
            return monday + datetime.timedelta(days=wd), "date"
        if re.search(r"\bthis\s+coming\s+" + WEEKDAYS[wd], t):
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
    # a year said digit by digit: "one nine eight nine"
    digits = [str(UNITS[w]) for w in toks if w in UNITS and UNITS[w] < 10]
    for i in range(len(toks) - 3):
        run4 = toks[i:i + 4]
        if all(w in UNITS and UNITS[w] < 10 for w in run4):
            y = int("".join(str(UNITS[w]) for w in run4))
            if 1900 <= y <= 2099:
                return y
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
    """Returns ('ok', 'YYYY-MM-DD') or ('partial', None) or ('bad', None). After a correction ('the 18th, sorry,
    I mean the 19th of October 1983') the corrected parts replace the ones said before."""
    t = (text or "").lower().strip()
    if not t:
        return "partial", None
    got, bad = {}, False
    parts = CORRECTION.split(t)
    for part in (parts if len(parts) > 1 else [t]):
        p = dob_parts(part, order)
        if p is None:
            bad = True  # a date that cannot exist: bad, unless a later part corrects it
            continue
        if p:
            bad = False
            got.update(p)
    if bad or not got:
        return "bad", None
    if "y" in got and "m" in got and "d" in got:
        try:
            return "ok", D(got["y"], got["m"], got["d"]).isoformat()
        except Exception:
            return "bad", None
    return "partial", None


def dob_parts(t, order):
    """The parts of a date of birth that one stretch of words names: some of 'y', 'm' and 'd'. None for a date
    given in full that cannot exist."""
    t2 = re.sub(r"[,]", " ", t)
    m = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", t2)
    if m:
        try:
            x = D(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return {"y": x.year, "m": x.month, "d": x.day}
        except Exception:
            return None
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
            x = D(y, mo, d)
            return {"y": x.year, "m": x.month, "d": x.day}
        except Exception:
            return None
    t2 = t2.replace("-", " ")
    mon = find_month(t2)
    year = parse_year_words(t2)
    t3 = re.sub(r"\b(19|20)\d\d\b", " ", t2)
    t3 = re.sub(r"\b(one|oh|zero|two)(\s+(zero|oh|one|two|three|four|five|six|seven|eight|nine)){3}\s*$", " ", t3)
    if year:
        # strip the year words so that "nineteen eighty-eight" does not look like a day
        t3 = re.sub(r"\b(nineteen|twenty|two thousand)(\s+(and\s+)?[a-z]+){0,2}\s*$", " ", t3)
    days = day_numbers(t3, cardinals=True)
    out = {}
    if year:
        out["y"] = year
    if mon:
        out["m"] = mon
    if days:
        out["d"] = days[0]
    return out


def parse_time(text):
    """'around eleven', '11', '2 pm', 'half past ten', '14:30', 'tonight after nine' -> 'HH:MM' or ''."""
    t = (text or "").lower().replace(".", ":")
    pm = bool(re.search(r"\b(pm|p m|afternoon|evening|tonight|night)\b", t))
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


# a number said as a time, and the words that name a day
TIME_WORDS = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\b\d{1,2}\s*(?:am|pm|a\s?m|p\s?m|o'?clock)\b"
                        r"|\b(?:at|around|about|after|before|by|from|until|till)\s+\d{1,2}\b", re.I)
DAY_WORDS = re.compile(r"\b(?:today|tonight|tomorrow|now|" + "|".join(WEEKDAYS + MONTHS + list(ORD)) + r")\b"
                       r"|\b\d{1,2}(?:st|nd|rd|th)\b|\b\d{1,2}[/.]\d{1,2}\b|\b\d{4}-\d{2}-\d{2}\b", re.I)


def callback_when(S, text, today):
    """The day and the time a callback phrase names. A number said as the time is not a day ('at 3 pm' is not the
    3rd), and a correction replaces only what it names ('tomorrow at 11, sorry, I mean 12'). Returns (date or None, 'HH:MM' or '')."""
    def part(t):
        tm = parse_time(t)
        d = None
        if not tm or DAY_WORDS.search(t):
            d = parse_day_phrase(S, TIME_WORDS.sub(" ", t) if tm else t, today)[0]
        return {"d": d, "tm": tm}
    got = corrected(text, part)
    return got.get("d"), got.get("tm") or ""


def spoken_amount(text):
    """An amount as said; after a correction ('two hundred, sorry, I mean two hundred and fifty') the corrected one."""
    return corrected(text, lambda t: {"a": to_float(t)}).get("a")


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


# ---------------------------------------------------------------- state and speaking

def load_state(V):
    st = jload(V.get("st"), None)
    return st if isinstance(st, dict) else None


def save(V, st):
    V["st"] = json.dumps(st)


def address(S, V):
    vals = {}
    for k in list(V.keys()):
        if isinstance(k, str) and len(k) < 40 and "." not in k:
            vals[k] = sval(V, k)
    return fill_template((S.get("variables") or {}).get("address_template") or "{title} {last_name}", vals).strip()


def join(*parts):
    return " ".join(p.strip() for p in parts if p and p.strip())


def say(V, st, node, *parts):
    """Every line the agent says is built here from the spec's phrases. The dialogue model is not asked to write it."""
    text = join(*parts)
    st["last_say"] = text
    V["say_line"] = text
    V["instruction"] = 'Say exactly: "' + text + '"'
    V["next_step"] = node + "_fixed"
    st["pending"] = node


def go_on(V, st, node):
    """The customer has not finished: a short prompt, no question, nothing counted. At most twice in a row."""
    if int(st.get("go_on") or 0) >= 2:
        return False
    st["go_on"] = int(st.get("go_on") or 0) + 1
    line = variant(st, "go_on")
    V["say_line"] = line
    V["instruction"] = 'Say exactly: "' + line + '"'
    V["next_step"] = node + "_fixed"
    st["pending"] = node
    return True


def repeat_last(V, st, node, *prefix):
    say(V, st, node, *(list(prefix) + [st.get("last_ask") or st.get("last_say") or ""]))


def ask(V, st, node, *parts):
    # a line that ends in a question the customer must answer; kept for repeating
    text = join(*parts)
    st["last_ask"] = text
    say(V, st, node, text)


def call_tool(S, V, st, tool, values):
    # values: role -> value. Fields come from the spec mapping, so a renamed field still works.
    for role, val in values.items():
        V["a_" + tool + "_" + tool_field(S, tool, role)] = "" if val is None else str(val)
    V["res_" + tool] = ""
    V["raw_" + tool] = ""
    V["route_" + tool] = "brain"
    st["sc_" + tool] = int(to_float(V.get("do_" + tool + "_success_count")) or 0)
    V["next_step"] = "do_" + tool
    st["pending"] = "tool:" + tool


def tool_result(V, tool, st=None):
    """The post-hook writes res_<tool>. If the hook did not run, the engine's own flattened copy
    do_<tool>_response.data.* is used, but only when the node's success counter moved since the dispatch."""
    for k in ("res_" + tool, "raw_" + tool):
        d = jload(V.get(k), None)
        if isinstance(d, dict):
            return d
    if st is not None and int(to_float(V.get("do_" + tool + "_success_count")) or 0) > int(st.get("sc_" + tool) or 0):
        pre = "do_" + tool + "_response.data."
        d = {}
        for k in list(V.keys()):
            if isinstance(k, str) and k.startswith(pre) and k.count(".") == 2:
                v = V.get(k)
                d[k[len(pre):]] = jload(v, v) if isinstance(v, str) and v[:1] in "[{" else v
        if d:
            return d
    return None


def tool_ok(S, tool, d):
    if not isinstance(d, dict):
        return False
    v = d.get(resp_field(S, tool, "ok"), True)
    return not falsy(v) and not d.get("error")


def warn(st, msg):
    st.setdefault("warnings", []).append(msg[:200])


def when_words(S, date_iso, today):
    if date_iso == today.isoformat():
        return phrase(S, "word_today") or "today"
    return phrase(S, "word_on_date", date=fmt_date(D.fromisoformat(date_iso), today)) or ("on " + fmt_date(D.fromisoformat(date_iso), today))


def answer_for_question(S, kind):
    if kind == "ai":
        return phrase(S, "ai_answer")
    if kind == "scam":
        return phrase(S, "scam_answer")
    if kind == "other":
        return phrase(S, "no_info")
    return ""


# ---------------------------------------------------------------- closing

def set_final(S, V, st):
    """The outcome close_call sends. Updated on every run, so a call that ends early still closes sensibly."""
    sit = st.get("situation") or ""
    prods = st.get("products") or []
    recorded = [p for p in prods if p.get("status") == "recorded"]
    if sit.startswith("custom:") and not recorded:
        c = custom_by_name(S, sit[len("custom:"):]) or {}
        outcome, reason = c.get("outcome") or "", c.get("reason") or ""
    elif sit.startswith("transfer_"):
        outcome, reason = outcome_for(S, sit)
    elif recorded:
        outcome, reason = outcome_for(S, "promise_recorded")
    elif sit:
        outcome, reason = outcome_for(S, sit)
    elif prods:
        notes = [p.get("note_sit") or p.get("status") for p in prods]
        if notes and all(n == "already_paid" for n in notes):
            outcome, reason = outcome_for(S, "already_paid")
        else:
            first = ""
            for n in notes:
                if n and n != "already_paid" and n in ("refused", "hardship", "dispute", "service_error"):
                    first = n
                    break
            outcome, reason = outcome_for(S, first or "refused")
    elif st.get("verified"):
        outcome, reason = outcome_for(S, "refused")
    elif st.get("phase") == "identity":
        outcome, reason = outcome_for(S, "id_declined")
    else:
        outcome, reason = outcome_for(S, "unclear")
    V["final_outcome"] = outcome
    V["final_reason"] = reason


def finish(S, V, st, situation, *lead):
    if situation:
        st["situation"] = situation
    set_final(S, V, st)
    V["farewell"] = join(*(list(lead) + [phrase(S, "goodbye")])) or "Goodbye."
    V["next_step"] = "bye"
    st["pending"] = "bye"


# ---------------------------------------------------------------- the brief's own situations (custom_situations)

def custom_by_name(S, name):
    for c in S.get("custom_situations") or []:
        if isinstance(c, dict) and c.get("name") == name:
            return c
    return None


def handle_custom(S, V, st, c, node):
    """Say the brief's text, then carry on, book a callback, or close with the situation's own outcome."""
    text = c.get("say_text") or ""
    if c.get("continue_for_promise"):
        return repeat_last(V, st, node, text)
    st["situation"] = "custom:" + c["name"]
    if c.get("needs_callback"):
        st["phase"] = "custom_cb"
        st["cb_asks"] = 0
        return ask(V, st, "talk_pre", text, c.get("callback_ask_text") or "")
    for p in st.get("products") or []:
        if p.get("status") in ("agreed", "confirmed"):
            p["status"] = "open"
    return finish(S, V, st, "custom:" + c["name"], text)


def on_custom_callback(S, V, st, now):
    text = sval(V, "cb_phrase")
    consume(V, ("presence", "cb_phrase", "q_kind"))
    tp = S.get("third_party") or {}
    today = now.date()
    d, tm = callback_when(S, text, today)
    if d is not None or tm:
        d = d or (D.fromisoformat(st["cb_day"]) if st.get("cb_day") else today)
        st["cb_day"] = d.isoformat()
        if tm and callback_ok(S, d, tm, now):
            st["cb"] = [d.isoformat(), tm]
            return call_tool(S, V, st, "schedule_callback", {"date": d.isoformat(), "time": tm})
    st["cb_asks"] = int(st.get("cb_asks") or 0) + 1
    if st["cb_asks"] >= int(tp.get("max_asks") or 2):
        return finish(S, V, st, "no_callback", phrase(S, "no_callback"))
    days = allowed_callback_days(S, now)
    ask(V, st, "talk_pre", phrase(S, "callback_other_time", days=" or ".join(fmt_date(x, today) for x in days),
                                  start=tp.get("window_start") or "", end=tp.get("window_end") or "", address=address(S, V)))


# ---------------------------------------------------------------- requests that can come at any time

def handle_human(S, V, st, node):
    req = (S.get("requests") or {}).get("human") or {}
    if not req.get("enabled", True) or not queue_for(S, "human"):
        return False
    st["human"] = int(st.get("human") or 0) + 1
    if st["human"] <= int(req.get("ask_help_first_times") or 0):
        say(V, st, node, phrase(S, "human_offer_help"))
        return True
    st["situation"] = "transfer_human"
    st["transfer_queue"] = queue_for(S, "human")
    for p in st.get("products") or []:
        if p.get("status") in ("agreed", "confirmed"):
            p["status"] = "open"
    call_tool(S, V, st, "transfer_to_agent", {"queue": st["transfer_queue"]})
    return True


def not_talking_rule(S):
    try:
        return int(((S.get("requests") or {}).get("not_talking") or {}).get("max_times") or 0)
    except Exception:
        return 0


def count_not_talking(S, st):
    """True when the brief's limit is reached. Without such a rule (0) it never closes the call by itself."""
    st["not_talking"] = int(st.get("not_talking") or 0) + 1
    mx = not_talking_rule(S)
    return mx > 0 and st["not_talking"] >= mx


# ---------------------------------------------------------------- phase: who is on the line

def identity_question(S, V):
    q = phrase(S, "identity_question", address=address(S, V))
    return fill_template(q, dict((k, sval(V, k)) for k in list(V.keys()) if isinstance(k, str) and len(k) < 40))


def on_presence(S, V, st, now):
    kind = sval(V, "presence")
    q = sval(V, "q_kind")
    cb = sval(V, "cb_phrase")
    consume(V, ("presence", "q_kind", "cb_phrase"))
    maxa = int((S.get("presence") or {}).get("max_asks") or 2)
    if kind == "deceased":
        return finish(S, V, st, "deceased", phrase(S, "condolence"))
    if kind == "wrong_number":
        return finish(S, V, st, "wrong_number", phrase(S, "wrong_number_ack"))
    if kind == "human" and handle_human(S, V, st, "talk_pre"):
        return
    if kind == "confirmed":
        st["phase"] = "identity"
        st["q_index"] = 0
        return ask_question(S, V, st)
    if kind == "other_person":
        st["phase"] = "third_party"
        st["cb_asks"] = 0
        if cb:
            V["cb_phrase"] = cb
            return on_third_party(S, V, st, now)
        return ask(V, st, "talk_pre", phrase(S, "third_party_ask", address=address(S, V)))
    if kind in ("not_talking", "refuses"):
        if count_not_talking(S, st):
            return finish(S, V, st, "id_declined")
    if st.get("_cut") and kind in ("", "unclear") and not q and go_on(V, st, "talk_pre"):
        return
    st["asks"] = int(st.get("asks") or 1) + 1
    if st["asks"] > maxa:
        return finish(S, V, st, "unclear")
    say(V, st, "talk_pre", answer_for_question(S, q), identity_question(S, V))


def on_third_party(S, V, st, now):
    kind = sval(V, "presence")
    text = sval(V, "cb_phrase")
    q = sval(V, "q_kind")
    consume(V, ("presence", "cb_phrase", "q_kind"))
    tp = S.get("third_party") or {}
    who = address(S, V)
    privacy = phrase(S, "third_party_privacy", address=who) if q in ("purpose", "other") or kind == "question" else ""
    if kind == "deceased":
        return finish(S, V, st, "deceased", phrase(S, "condolence"))
    if kind == "wrong_number":
        return finish(S, V, st, "wrong_number", phrase(S, "wrong_number_ack"))
    if kind == "confirmed" and not text:
        st["phase"] = "identity"
        st["q_index"] = 0
        return ask_question(S, V, st)
    if not tp.get("callback_enabled", True):
        return finish(S, V, st, "no_callback")
    today = now.date()
    if st.get("cb_frag"):
        text = join(st.pop("cb_frag"), text)
    d, tm = callback_when(S, text, today)
    if st.get("_cut") and not (d is not None and tm):
        st["cb_frag"] = text
        if go_on(V, st, "talk_pre"):
            return
        st.pop("cb_frag", None)
    if d is None and not tm:
        if kind in ("refuses", "not_talking"):
            return finish(S, V, st, "no_callback", phrase(S, "no_callback"))
        st["cb_vague"] = int(st.get("cb_vague") or 0) + 1
        if st["cb_vague"] > 2:
            return finish(S, V, st, "no_callback", phrase(S, "no_callback"))
        return ask(V, st, "talk_pre", privacy, phrase(S, "third_party_ask", address=who))
    if d is None:
        d = st.get("cb_day") and D.fromisoformat(st["cb_day"]) or today
    st["cb_day"] = d.isoformat()
    if not tm and d in allowed_callback_days(S, now):
        return ask(V, st, "talk_pre", privacy, phrase(S, "ask_callback_time", date=fmt_date(d, today), address=who))
    # a day outside the callback days needs no time: it is outside the window, and another time is asked once
    if callback_ok(S, d, tm, now):
        st["cb"] = [d.isoformat(), tm]
        return call_tool(S, V, st, "schedule_callback", {"date": d.isoformat(), "time": tm})
    st["cb_asks"] = int(st.get("cb_asks") or 0) + 1
    if st["cb_asks"] >= int(tp.get("max_asks") or 2):
        return finish(S, V, st, "no_callback", phrase(S, "no_callback"))
    days = allowed_callback_days(S, now)
    ask(V, st, "talk_pre", privacy, phrase(S, "callback_other_time", days=" or ".join(fmt_date(x, today) for x in days),
                                           start=tp.get("window_start") or "", end=tp.get("window_end") or "", address=who))


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
    first = [today] if is_bday(S, today) else []
    return first + [next_bday(S, today, include=False)]


def callback_ok(S, d, tm, now):
    tp = S.get("third_party") or {}
    if d not in allowed_callback_days(S, now):
        return False
    if not ((tp.get("window_start") or "00:00") <= tm <= (tp.get("window_end") or "23:59")):
        return False
    if tp.get("after_now", True) and d == now.date() and tm <= now.strftime("%H:%M"):
        return False
    return True


# ---------------------------------------------------------------- phase: identity

def questions(S):
    return [q for q in (((S.get("identity") or {}).get("questions")) or []) if isinstance(q, dict) and q.get("field")]


def simple_question(q, st=None):
    """A shorter way to ask the same question, from its answer type (the builder's own words)."""
    st = st if st is not None else {}
    t = q.get("answer_type")
    if t == "date":
        return variant(st, "date")
    if t == "digits":
        n = int(q.get("digits_length") or 0)
        return variant(st, "digits", n=n) if n else variant(st, "digits_any")
    if t == "year":
        return variant(st, "year_only")
    return "Just that, please: " + (q.get("ask_text") or "")


UNCLEAR_LIMIT = 4  # the builder's own limit: unclear or off-topic answers in the identity step before the call closes


def missing_part(q, partial, st=None):
    """Ask only for what is still missing of an answer given in parts (the builder's own words)."""
    st = st if st is not None else {}
    t = q.get("answer_type")
    if t == "date":
        p = (partial or "").lower()
        if not parse_year_words(p):
            return variant(st, "year_only")
        if not find_month(p):
            return variant(st, "month_only")
        return variant(st, "day_only")
    if t == "digits":
        n = int(q.get("digits_length") or 0)
        have = len(words_to_digits(partial or ""))
        if n and have < n:
            return variant(st, "rest_digits", k=n - have)
    return variant(st, "rest")


def unclear_identity(S, V, st):
    """Unclear or off-topic is never a refusal. The question is asked again, alternating a simpler form and the
    spec's own words. After UNCLEAR_LIMIT unclear answers in a row the call closes as the spec's 'unclear'."""
    qs = questions(S)
    i = int(st.get("q_index") or 0)
    st["id_unclear"] = int(st.get("id_unclear") or 0) + 1
    if st["id_unclear"] > UNCLEAR_LIMIT:
        return finish(S, V, st, "unclear")
    if st.get("id_partial") and i < len(qs):
        return say(V, st, "talk_id", missing_part(qs[i], st["id_partial"], st))
    if st["id_unclear"] % 2 == 1 and i < len(qs):
        return say(V, st, "talk_id", simple_question(qs[i], st))
    return ask_question(S, V, st, not_understood(S, st))


def ask_question(S, V, st, *prefix):
    qs = questions(S)
    i = int(st.get("q_index") or 0)
    if i >= len(qs):
        return start_account(S, V, st)
    st["id_partial"] = ""
    ask(V, st, "talk_id", *(list(prefix) + [qs[i].get("ask_text") or ""]))


def normalize_answer(q, raw, iso_hint):
    typ = q.get("answer_type") or "text"
    iso_ok = bool(iso_hint and re.match(r"^\d{4}-\d{2}-\d{2}$", iso_hint))
    if typ == "date":
        status, val = parse_dob(raw, q.get("numeric_date_order") or "DMY")
        if status == "ok":
            return status, val
        if iso_ok and (not raw or status == "bad" or parse_year_words(raw)):
            return "ok", iso_hint
        return status if raw else "empty", None
    if typ == "digits":
        n = int(q.get("digits_length") or 0)
        dg = corrected(raw, lambda t: {"dg": words_to_digits(t)}).get("dg") or ""
        if not dg:
            return ("partial" if raw else "empty"), None
        if n and len(dg) < n:
            return "partial", None
        return "ok", dg[-n:] if n else dg
    if typ == "year":
        y = corrected(raw, lambda t: {"y": parse_year_words(t)}).get("y")
        return ("ok", str(y)) if y else (("partial" if raw else "empty"), None)
    v = corrected(raw, lambda t: {"v": t.strip(" ,;:")}).get("v") or ""
    return ("ok", v) if v else ("empty", None)


def restarts(q, partial, raw):
    """'44', then '440': the customer said the number again from the start. '463', then '51' is its second part."""
    if (q.get("answer_type") or "") != "digits":
        return False
    a, b = words_to_digits(partial), words_to_digits(raw)
    return bool(a) and len(b) > len(a) and b.startswith(a)


def on_identity_turn(S, V, st):
    raw = sval(V, "id_answer")
    iso = sval(V, "id_iso")
    rk = sval(V, "id_reply")
    q = sval(V, "q_kind")
    last = sval(V, "last_message")
    consume(V, ("id_answer", "id_iso", "id_reply", "q_kind", "last_message"))
    if rk in ("answer", "") and not raw and last:
        raw = last  # the extraction marked an answer but gave no text: use the message itself
    m = re.match(r"^--(\d{2})-(\d{2})$", iso)
    if m:
        # day and month without a year: keep them as words, they join with a year said later
        raw = join(raw, str(int(m.group(2))) + " " + MONTHS[int(m.group(1)) - 1]) if 1 <= int(m.group(1)) <= 12 else raw
        iso = ""
    idn = S.get("identity") or {}
    if rk == "human" and handle_human(S, V, st, "talk_id"):
        return
    if rk == "not_talking":
        if count_not_talking(S, st):
            return finish(S, V, st, "id_declined")
        rk = "refuse"
    if rk == "already_given":
        # annoyed, not refusing: say sorry and ask only for what is missing
        qs = questions(S)
        i = int(st.get("q_index") or 0)
        if iso and re.match(r"^\d{4}-\d{2}-\d{2}$", iso):
            rk, raw = "answer", raw or iso
        elif i < len(qs):
            st["id_unclear"] = 0
            part = st.get("id_partial") or ""
            return say(V, st, "talk_id", variant(st, "sorry"), missing_part(qs[i], part, st) if part else simple_question(qs[i], st))
    if rk == "asks_purpose" and not raw:
        rk = "refuse" if idn.get("purpose_question_is_refusal", True) else "question"
    if rk == "refuse" and not raw:
        st["refusals"] = int(st.get("refusals") or 0) + 1
        if st["refusals"] >= int(idn.get("max_refusals") or 2):
            return finish(S, V, st, "id_declined")
        return ask_question(S, V, st, phrase(S, "decline_explain"))
    qs = questions(S)
    i = int(st.get("q_index") or 0)
    if i >= len(qs):
        return start_account(S, V, st)
    if st.get("_cut") and not raw and not iso and rk in ("", "unclear", "answer") and go_on(V, st, "talk_id"):
        return
    if rk == "answer" and not raw and not iso:
        # marked as an answer but nothing came through: not unclear; wait for it and keep any stored part
        if go_on(V, st, "talk_id"):
            return
        qs = questions(S)
        i = int(st.get("q_index") or 0)
        if st.get("id_partial") and i < len(qs):
            return say(V, st, "talk_id", missing_part(qs[i], st["id_partial"], st))
    if rk == "question" and not raw and not iso:
        ans = (phrase(S, "purpose_answer") or phrase(S, "no_info")) if q == "purpose" or not q else (answer_for_question(S, q) or phrase(S, "no_info"))
        return ask_question(S, V, st, ans)
    partial = st.get("id_partial") or ""
    if partial and restarts(qs[i], partial, raw):
        partial = ""  # the number said again from the start: not a second part to add
    joined = join(partial, raw)
    status, val = normalize_answer(qs[i], joined, iso)
    if status == "ok" and st.get("_cut") and qs[i].get("answer_type") == "digits" and not qs[i].get("digits_length"):
        status = "partial"  # a number of no fixed length that broke off: wait for the rest before sending it
    if status == "ok":
        st["id_partial"] = ""
        st["id_last"] = val
        st["id_unclear"] = 0
        return call_tool(S, V, st, "verify_identity", {"field": qs[i]["field"], "answer": val})
    if status == "partial":
        st["id_partial"] = joined
        st["id_unclear"] = 0
        if st.get("_cut") and go_on(V, st, "talk_id"):
            return
        return say(V, st, "talk_id", missing_part(qs[i], joined, st))
    st["id_partial"] = ""
    return unclear_identity(S, V, st)


def on_verify_result(S, V, st):
    d = tool_result(V, "verify_identity", st)
    idn = S.get("identity") or {}
    qs = questions(S)
    i = min(int(st.get("q_index") or 0), max(0, len(qs) - 1))
    if d is None:
        st["verify_errors"] = int(st.get("verify_errors") or 0) + 1
        if st["verify_errors"] <= 2 and st.get("id_last"):
            return call_tool(S, V, st, "verify_identity", {"field": qs[i]["field"], "answer": st["id_last"]})
        return ask_question(S, V, st, not_understood(S, st))
    hint = str(d.get(resp_field(S, "verify_identity", "hint")) or "").strip()
    if hint.lower() in ("none", "null", "false"):
        hint = ""
    verified = truthy(d.get(resp_field(S, "verify_identity", "verified")))
    allv = truthy(d.get(resp_field(S, "verify_identity", "all_verified")))
    left = to_float(d.get(resp_field(S, "verify_identity", "wrong_answers_left")))
    if not tool_ok(S, "verify_identity", d) and not verified:
        # the service could not read the answer: not a wrong answer
        return ask_question(S, V, st, phrase(S, "unreadable_answer"))
    if allv or (verified and i + 1 >= len(qs)):
        st["verified"] = True
        return start_account(S, V, st)
    if verified:
        st["q_index"] = i + 1
        st["id_unclear"] = 0
        return ask_question(S, V, st)
    for h in idn.get("hints") or []:
        if hint and h.get("value") == hint and not h.get("counts_as_wrong", False):
            st["last_ask"] = h.get("instruction") or ""
            return say(V, st, "talk_id", h.get("instruction") or not_understood(S, st))
    st["wrong"] = int(st.get("wrong") or 0) + 1
    if (left is not None and left <= 0) or st["wrong"] >= int(idn.get("max_wrong_total") or 3):
        return finish(S, V, st, "id_failed", phrase(S, "id_failed"))
    return ask_question(S, V, st, phrase(S, "wrong_answer"))


# ---------------------------------------------------------------- phase: the account

def start_account(S, V, st):
    st["phase"] = "account"
    call_tool(S, V, st, "get_account", {})


def on_account_result(S, V, st, now):
    d = tool_result(V, "get_account", st)
    raw = products_from_result(S, d) if d is not None else []
    if not raw:
        st["account_errors"] = int(st.get("account_errors") or 0) + 1
        if st["account_errors"] <= 2:
            return start_account(S, V, st)
        return finish(S, V, st, "service_error", phrase(S, "service_error", product=""))
    st["products"] = plan_products(S, raw, now.date())
    st["phase"] = "main"
    st["stage"] = "ask_today"
    st["cur"] = 0
    lines = [phrase(S, "debt_intro")]
    for p in st["products"]:
        lines.append(phrase(S, "debt_line", product=p["spoken"], amount=fmt_amount(p["due"]), days=p["late"]))
    multi = len(st["products"]) > 1
    question = phrase(S, "pay_all_today" if multi else "pay_today")
    say(V, st, "talk_main", *(lines + [question]))
    st["last_ask"] = question  # a repeat asks the question again, not the whole statement


# ---------------------------------------------------------------- phase: getting the promise

def open_products(st):
    return [p for p in st.get("products") or [] if p.get("status") == "open"]


def current(st):
    ps = st.get("products") or []
    i = int(st.get("cur") or 0)
    while i < len(ps) and ps[i].get("status") != "open":
        i += 1
    if i >= len(ps):
        i = 0
        while i < len(ps) and ps[i].get("status") != "open":
            i += 1
    st["cur"] = i
    return ps[i] if i < len(ps) else None


def attempt_spec(S, p, n):
    for a in sorted([a for a in ((S.get("persuasion") or {}).get("attempts") or []) if isinstance(a, dict)], key=lambda a: int(a.get("n") or 0)):
        if int(a.get("n") or 0) == n and (not a.get("bands") or p.get("band") in a.get("bands")):
            return a
    return None


def attempt_date(S, p, spec, today):
    dl = D.fromisoformat(p["deadline"])
    kind = (spec or {}).get("date") or "deadline"
    d = resolve_named_date(S, kind, today, dl)
    if d is None or (d == today and kind in ("end_of_this_week", "end_of_next_week")):
        d = resolve_named_date(S, (spec or {}).get("if_today_is_that_date") or "end_of_next_week", today, dl)
    if d is None or d > dl:
        d = dl
    return max(d, today)


def make_offer(S, V, st, p, amount, date_iso, today, *lead):
    p["offer"] = [round(float(amount), 2), date_iso]
    st["stage"] = "offer"
    multi = len(st.get("products") or []) > 1
    question = phrase(S, "offer", amount=fmt_amount(amount), when=when_words(S, date_iso, today),
                      product=(p["spoken"] if multi else ""), for_product=(phrase(S, "for_product", product=p["spoken"]) if multi else ""))
    say(V, st, "talk_main", *(list(lead) + [question]))
    st["last_ask"] = question  # a repeat asks only the question, without the lead (the floor note is said once)


def attempt_offer(S, V, st, p, today, *lead):
    """A flat refusal: use the next persuasion attempt, or stop."""
    while int(p.get("used") or 0) < int(p.get("attempts") or 1):
        p["used"] = int(p.get("used") or 0) + 1
        spec = attempt_spec(S, p, p["used"])
        if spec is None:
            continue
        kind = spec.get("amount") or "full"
        amount = p["floor"] if kind == "floor" or (kind == "full_or_floor_if_too_much" and p.get("too_much")) else p["due"]
        d = attempt_date(S, p, spec, today)
        if [round(float(amount), 2), d.isoformat()] in (p.get("refused") or []):
            continue
        return make_offer(S, V, st, p, amount, d.isoformat(), today, *lead)
    p["status"] = "refused"
    return next_product(S, V, st, today, *lead)


def check_date(S, p, d, today):
    """(date to use or None, problem) for a day the customer named."""
    dl = D.fromisoformat(p["deadline"])
    earliest = today if ((S.get("promise_date") or {}).get("earliest") or "today") == "today" else today + datetime.timedelta(days=1)
    if d < earliest:
        return None, "past"
    if d > dl:
        return dl, "after_deadline"
    if not is_bday(S, d):
        nb = prev_bday(S, d) if (S.get("promise_date") or {}).get("non_business") == "offer_previous_business_day" else next_bday(S, d)
        if nb > dl:
            nb = prev_bday(S, dl)
        if nb < earliest:
            nb = next_bday(S, earliest)
        return nb, "non_business"
    return d, ""


def agree(S, V, st, p, amount, date_iso, today):
    p["amount"] = round(float(amount), 2)
    p["date"] = date_iso
    p["status"] = "agreed"
    p["offer"] = None
    if st.get("stage") == "ask_today" and len(st.get("products") or []) > 1 and open_products(st):
        # one product settled in answer to the shared question: the others now go one at a time
        return next_product(S, V, st, today, ONE_AT_A_TIME)
    return next_product(S, V, st, today)


def next_product(S, V, st, today, *lead):
    p = current(st)
    if p is not None:
        if not p.get("entered"):
            p["entered"] = True
            return attempt_offer(S, V, st, p, today, *lead)
        if p.get("offer"):
            return make_offer(S, V, st, p, p["offer"][0], p["offer"][1], today, *lead)
        return attempt_offer(S, V, st, p, today, *lead)
    return readback(S, V, st, today, *lead)


def readback(S, V, st, today, *lead):
    agreed = [p for p in st.get("products") or [] if p.get("status") == "agreed"]
    if not agreed:
        return after_records(S, V, st, today, *lead)
    items = []
    for p in agreed:
        s = phrase(S, "promise_item", amount=fmt_amount(p["amount"]), product=p["spoken"], when=when_words(S, p["date"], today))
        if p.get("clamped"):
            s = join(s, "(" + phrase(S, "clamp_note", product=p["spoken"], date=fmt_date(D.fromisoformat(p["date"]), today)) + ")")
        items.append(s)
    listing = items[0] if len(items) == 1 else "; ".join(items[:-1]) + "; " + items[-1]
    st["stage"] = "confirm"
    ask(V, st, "talk_main", *(list(lead) + [phrase(S, "readback", items=listing), phrase(S, "confirm_question")]))


def record_next(S, V, st, today):
    for p in st.get("products") or []:
        if p.get("status") == "confirmed":
            st["recording"] = p["id"]
            return call_tool(S, V, st, "create_promise", {"product_id": p["id"], "amount": p["amount"], "date": p["date"]})
    return after_records(S, V, st, today)


def on_promise_result(S, V, st, today):
    d = tool_result(V, "create_promise", st)
    p = next((x for x in st.get("products") or [] if x.get("id") == st.get("recording")), None)
    if p is None:
        return after_records(S, V, st, today)
    if tool_ok(S, "create_promise", d):
        p["status"] = "recorded"
        return record_next(S, V, st, today)
    if d is not None and p.get("unknown") and "already" in str(d.get("error") or "").lower():
        # the earlier attempt got no answer but reached the bank: the bank now says the promise exists
        p["status"] = "recorded"
        return record_next(S, V, st, today)
    if d is None:
        p["unknown"] = True
    p["retries"] = int(p.get("retries") or 0) + 1
    if p["retries"] <= int((S.get("promise") or {}).get("retries") or 1):
        # try again at once, in the same turn: the tool node goes straight to the tool node
        p["had_failure"] = True
        return call_tool(S, V, st, "create_promise", {"product_id": p["id"], "amount": p["amount"], "date": p["date"]})
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


def after_records(S, V, st, today, *lead):
    if lead:
        st["lead"] = join(st.get("lead") or "", *lead)
    if notes_enabled(S) and not str(st.get("situation") or "").startswith("transfer_"):
        for p in st.get("products") or []:
            if p.get("status") == "recorded" or p.get("noted"):
                continue
            sit = p.get("note_sit") or ("refused" if p.get("status") in ("refused", "open", "agreed", "confirmed") else p.get("status"))
            p["noted"] = True
            p["note_sit"] = sit
            reason = note_reason(S, sit)
            if not reason:
                warn(st, "no note reason for " + str(sit))
                continue
            return call_tool(S, V, st, "add_note", {"product_id": p["id"], "reason": reason, "text": sit})
    return closing_words(S, V, st, today)


def closing_words(S, V, st, today):
    prods = st.get("products") or []
    rec = [p for p in prods if p.get("status") == "recorded"]
    failed = [p for p in prods if p.get("status") == "failed"]
    lines = [st.pop("lead", "") or ""]
    if rec:
        retried = [p for p in rec if p.get("had_failure")]
        plain = [p for p in rec if not p.get("had_failure")]
        if plain or len(rec) > 1:
            items = [phrase(S, "promise_item", amount=fmt_amount(p["amount"]), product=p["spoken"], when=when_words(S, p["date"], today)) for p in (plain if retried else rec)]
            if items:
                lines.append(phrase(S, "recorded", items="; ".join(items)))
        if retried:
            lines.append(RETRIED_OK)
        lines.append(phrase(S, "after_promise"))
    if failed:
        lines.append(NOT_SAVED_FINAL)
        lines.append(phrase(S, "service_error", product=", ".join(p["spoken"] for p in failed)))
    return finish(S, V, st, st.get("situation") or "", *lines)


def mark_open(st, status, sit=None):
    for x in st.get("products") or []:
        if x.get("status") == "open":
            x["status"] = status
            x["note_sit"] = sit or status


def on_main_turn(S, V, st, now):
    today = now.date()
    reply = sval(V, "reply")
    dphrase = sval(V, "date_phrase")
    V["_amount_raw"] = sval(V, "amount")
    amount = spoken_amount(sval(V, "amount"))
    allp = sval(V, "applies_to_all")
    q = sval(V, "q_kind")
    consume(V, ("reply", "date_phrase", "amount", "applies_to_all", "q_kind"))
    frag_d, frag_a, frag_r = st.pop("frag_date", ""), st.pop("frag_amount", ""), st.pop("frag_reply", "")
    if frag_d and dphrase:
        both = join(frag_d, dphrase)
        if parse_day_phrase(S, both, today)[0] is not None:
            dphrase = both
    elif frag_d and not dphrase and not dangling_date(frag_d):
        dphrase = frag_d
    if frag_r in ("yes", "no") and reply in ("", "other") and not dphrase:
        reply = frag_r  # the cut-off message said yes or no before the date words broke off
    raw_amount = sval(V, "_amount_raw")
    if frag_a and amount is not None:
        a2 = spoken_amount(join(frag_a, raw_amount))
        amount = a2 if a2 is not None else amount
    elif frag_a and amount is None:
        amount = spoken_amount(frag_a)
    stage = st.get("stage") or "ask_today"
    prods = st.get("products") or []
    multi = len(prods) > 1
    rq = S.get("requests") or {}
    p = current(st)
    d, dkind = parse_day_phrase(S, dphrase, today) if dphrase else (None, "none")
    proposes = d is not None or amount is not None
    if st.get("_cut") and not q and reply in ("", "other", "vague", "propose", "yes", "no"):
        # a cut-off message: keep its date and amount words and wait for the rest, unless it already says enough
        complete_date = d is not None and dkind == "date" and not dangling_date(dphrase)
        if not complete_date and not (reply in ("yes", "no") and not dphrase and amount is None):
            if dphrase:
                st["frag_date"] = dphrase
            if reply in ("yes", "no"):
                st["frag_reply"] = reply
            if raw_amount:
                st["frag_amount"] = raw_amount
            if go_on(V, st, "talk_main"):
                return
            st.pop("frag_date", None); st.pop("frag_amount", None)
    if reply not in ("", "other") or proposes:
        st["main_unclear"] = 0

    # while the hardship transfer is offered, only a clear yes transfers; everything else declines it
    if stage == "hardship_offer" and reply in ("restructuring", "human", "question", "other", "no", "not_talking", "too_much"):
        reply = "no"
    # requests that end or redirect the call come first
    if reply == "restructuring" and (rq.get("restructuring") or {}).get("enabled", True) and queue_for(S, "restructuring"):
        for x in prods:
            if x.get("status") in ("agreed", "confirmed"):
                x["status"] = "open"
        st["situation"] = "transfer_restructuring"
        st["transfer_queue"] = queue_for(S, "restructuring")
        return call_tool(S, V, st, "transfer_to_agent", {"queue": st["transfer_queue"]})
    if reply == "human" and handle_human(S, V, st, "talk_main"):
        return
    if stage == "hardship_offer":
        if reply in ("yes",) and not proposes:
            st["situation"] = "transfer_support"
            st["transfer_queue"] = queue_for(S, "hardship")
            return call_tool(S, V, st, "transfer_to_agent", {"queue": st["transfer_queue"]})
        if not proposes:
            # anything but a clear yes declines the transfer; no persuasion follows
            mark_open(st, "hardship")
            if not multi:
                st["situation"] = "hardship"
            return readback(S, V, st, today)
        st["stage"] = "offer"
        stage = "offer"
    if reply == "hardship" and not proposes and (S.get("hardship") or {}).get("enabled", True):
        hs = S.get("hardship") or {}
        if hs.get("offer_transfer", True) and queue_for(S, "hardship") and not st.get("hardship_offered"):
            st["hardship_offered"] = True
            st["stage"] = "hardship_offer"
            return ask(V, st, "talk_main", phrase(S, "hardship_sympathy"), phrase(S, "hardship_offer_transfer"))
        mark_open(st, "hardship")
        if not multi:
            st["situation"] = "hardship"
        return readback(S, V, st, today, "" if st.get("hardship_offered") else phrase(S, "hardship_sympathy"))
    if reply == "already_paid" and (rq.get("already_paid") or {}).get("enabled", True):
        lead = phrase(S, "already_paid")
        if multi and p is not None and stage != "ask_today":
            p["status"] = "already_paid"
            p["note_sit"] = "already_paid"
            return next_product(S, V, st, today, lead)
        mark_open(st, "already_paid")
        if not multi:
            st["situation"] = "already_paid"
        return readback(S, V, st, today, lead)
    if reply == "dispute" and (rq.get("dispute") or {}).get("enabled", True):
        lead = phrase(S, "dispute_ack")
        if multi and p is not None and stage != "ask_today":
            p["status"] = "dispute"
            p["note_sit"] = "dispute"
            return next_product(S, V, st, today, lead)
        mark_open(st, "dispute")
        if not multi:
            st["situation"] = "dispute"
        return readback(S, V, st, today, lead)
    if reply == "not_talking" and not proposes and not_talking_rule(S) <= 0:
        reply = "no"  # no rule for it in the brief: it is a refusal like any other
    if reply == "not_talking" and not proposes:
        if count_not_talking(S, st):
            mark_open(st, "refused")
            for x in prods:
                if x.get("status") == "agreed":
                    x["status"] = "refused"
                    x["note_sit"] = "refused"
            return readback(S, V, st, today)
        return repeat_last(V, st, "talk_main", phrase(S, "not_talking_ack"))
    if reply == "change_recorded":
        return repeat_last(V, st, "talk_main", phrase(S, "changes_after_record"))

    # the read-back
    if stage == "confirm" and (reply not in ("", "other") or proposes):
        st["confirm_unclear"] = 0
    if stage == "confirm":
        if reply == "yes" and not proposes:
            for x in prods:
                if x.get("status") == "agreed":
                    x["status"] = "confirmed"
            return record_next(S, V, st, today)
        if proposes:
            agreed = [x for x in prods if x.get("status") == "agreed"]
            if agreed:
                target = agreed[-1] if not multi else (agreed[-1] if allp != "yes" else agreed[0])
                target["status"] = "open"
                target["offer"] = [target["amount"], target["date"]]
                st["cur"] = prods.index(target)
                p = target
                stage = st["stage"] = "offer"
        elif reply == "no":
            agreed = [x for x in prods if x.get("status") == "agreed"]
            for x in agreed:
                x["status"] = "open"
                x["refused"] = (x.get("refused") or []) + [[x["amount"], x["date"]]]
            p = current(st)
            if p is None:
                return readback(S, V, st, today)
            st["stage"] = "offer"
            return attempt_offer(S, V, st, p, today)
        elif q:
            return repeat_last(V, st, "talk_main", answer_for_question(S, q) or phrase(S, "no_info"))
        else:
            return confirm_unclear(S, V, st, prods, today)

    if p is None:
        return readback(S, V, st, today)

    # a date or an amount from the customer is never a refusal
    if d is None and (dkind == "vague" or reply == "vague") and amount is None:
        p["vague"] = int(p.get("vague") or 0) + 1
        if p["vague"] <= int((S.get("promise_date") or {}).get("vague_ask_times") or 1):
            return ask(V, st, "talk_main", phrase(S, "ask_exact_day", product=p["spoken"]))
        amt = p["offer"][0] if p.get("offer") else (p["floor"] if p.get("too_much") else p["due"])
        return make_offer(S, V, st, p, amt, p["deadline"], today)
    if reply == "too_much" and not proposes:
        p["too_much"] = True
        if int(p.get("floor_offered") or 0) < int((S.get("amounts") or {}).get("floor_offer_times") or 1) and p["floor"] < p["due"]:
            p["floor_offered"] = int(p.get("floor_offered") or 0) + 1
            date_iso = p["offer"][1] if p.get("offer") and p["offer"][1] else attempt_date(S, p, attempt_spec(S, p, 1), today).isoformat()
            return make_offer(S, V, st, p, p["floor"], date_iso, today, phrase(S, "floor_caveat", amount=fmt_amount(p["floor"])))
        reply = "no"
    if proposes:
        base_amt = p["offer"][0] if p.get("offer") else (p["floor"] if p.get("too_much") else p["due"])
        base_date = p["offer"][1] if p.get("offer") and p["offer"][1] else None
        if stage == "ask_today" and base_date is None and reply == "yes" and d is None:
            base_date = today.isoformat()
        a = base_amt
        if amount is not None:
            if amount > p["due"] + 0.005:
                a = p["due"]
            elif amount + 0.005 < p["floor"]:
                if int(p.get("below_offered") or 0) < int((S.get("amounts") or {}).get("below_floor_offer_times") or 1):
                    p["below_offered"] = int(p.get("below_offered") or 0) + 1
                    if d is not None:
                        ok_d, _ = check_date(S, p, d, today)
                        date_iso = (ok_d or today).isoformat()
                    else:
                        date_iso = base_date or attempt_date(S, p, attempt_spec(S, p, 1), today).isoformat()
                    return make_offer(S, V, st, p, p["floor"], date_iso, today, phrase(S, "below_floor", amount=fmt_amount(p["floor"])))
                return refusal(S, V, st, p, today)
            else:
                a = round(amount, 2)
        if d is None:
            if base_date is None:
                p["offer"] = [a, None]
                return ask(V, st, "talk_main", phrase(S, "ask_day_for_amount", amount=fmt_amount(a), product=p["spoken"]))
            d = D.fromisoformat(base_date)
        ok_d, problem = check_date(S, p, d, today)
        if ok_d is None:
            return ask(V, st, "talk_main", phrase(S, "past_date"))
        everyone = multi and len(open_products(st)) > 1 and (allp == "yes" or (stage == "ask_today" and allp != "no"))
        if everyone and not (S.get("multi_product") or {}).get("clamp_to_deadline", True):
            # one day for everything, but the brief has no rule to move a product to its own deadline: the day goes
            # to every product it is valid for; the others get their own offer in turn
            for x in open_products(st):
                x_d, x_prob = check_date(S, x, d, today)
                if x_d is not None and not x_prob:
                    x["amount"] = a if x is p else (x["offer"][0] if x.get("offer") else (x["floor"] if x.get("too_much") else x["due"]))
                    x["date"], x["status"], x["offer"], x["entered"] = x_d.isoformat(), "agreed", None, True
            rest = open_products(st)
            if not rest:
                return readback(S, V, st, today)
            x = current(st)
            x["entered"] = True
            x_d, x_prob = check_date(S, x, d, today)
            amt = x["offer"][0] if x.get("offer") else x["due"]
            if x_d is None:
                return attempt_offer(S, V, st, x, today)
            lead = phrase(S, "latest_date", date=fmt_date(x_d, today)) if x_prob == "after_deadline" else \
                phrase(S, "not_business_day", date=fmt_date(d, today), next=fmt_date(x_d, today))
            return make_offer(S, V, st, x, amt, x_d.isoformat(), today, lead)
        if everyone and problem in ("", "after_deadline") and (S.get("multi_product") or {}).get("clamp_to_deadline", True):
            for x in open_products(st):
                x_d, x_prob = check_date(S, x, d, today)
                x["clamped"] = x_prob == "after_deadline"
                x["amount"] = a if x is p else (x["offer"][0] if x.get("offer") else (x["floor"] if x.get("too_much") else x["due"]))
                x["date"] = (x_d or d).isoformat()
                x["status"] = "agreed"
                x["offer"] = None
            return readback(S, V, st, today)
        if problem == "after_deadline":
            return make_offer(S, V, st, p, a, ok_d.isoformat(), today, phrase(S, "latest_date", date=fmt_date(ok_d, today)))
        if problem == "non_business":
            return make_offer(S, V, st, p, a, ok_d.isoformat(), today, phrase(S, "not_business_day", date=fmt_date(d, today), next=fmt_date(ok_d, today)))
        return agree(S, V, st, p, a, ok_d.isoformat(), today)
    if reply == "yes":
        if stage == "ask_today":
            ok_today, problem = check_date(S, p, today, today)
            if problem == "non_business" and ok_today is not None:
                # a call on a weekend or a holiday: today is not a payment day, offer the next one
                return make_offer(S, V, st, p, p["due"], ok_today.isoformat(), today,
                                  phrase(S, "not_business_day", date=fmt_date(today, today), next=fmt_date(ok_today, today)))
            for x in open_products(st):
                x["amount"], x["date"], x["status"], x["offer"] = x["due"], today.isoformat(), "agreed", None
            return readback(S, V, st, today)
        if p.get("offer") and p["offer"][1]:
            return agree(S, V, st, p, p["offer"][0], p["offer"][1], today)
        return repeat_last(V, st, "talk_main")
    if reply == "no":
        return refusal(S, V, st, p, today)
    if q or reply == "question":
        st["main_unclear"] = 0
        return repeat_last(V, st, "talk_main", answer_for_question(S, q) or phrase(S, "no_info"))
    # not understood: a short hint first, then the spec's words; the third time it is a non-answer (a refusal)
    st["main_unclear"] = int(st.get("main_unclear") or 0) + 1
    if st["main_unclear"] == 1:
        return say(V, st, "talk_main", st.get("last_ask") or "", variant(st, "yes_no"))
    if st["main_unclear"] == 2:
        return repeat_last(V, st, "talk_main", not_understood(S, st))
    st["main_unclear"] = 0
    return refusal(S, V, st, p, today)


def confirm_unclear(S, V, st, prods, today):
    """The read-back got no clear answer. Up to UNCLEAR_LIMIT times it is read again (every second time with the
    spec's 'not understood'); then it is not confirmed, as a no would be, and the spec's attempts decide."""
    st["confirm_unclear"] = int(st.get("confirm_unclear") or 0) + 1
    if st["confirm_unclear"] <= UNCLEAR_LIMIT:
        return repeat_last(V, st, "talk_main", not_understood(S, st) if st["confirm_unclear"] % 2 == 0 else "")
    st["confirm_unclear"] = 0
    for x in [x for x in prods if x.get("status") == "agreed"]:
        x["status"] = "open"
        x["refused"] = (x.get("refused") or []) + [[x["amount"], x["date"]]]
    p = current(st)
    if p is None:
        return readback(S, V, st, today)
    st["stage"] = "offer"
    return attempt_offer(S, V, st, p, today)


def refusal(S, V, st, p, today):
    if p.get("offer") and p["offer"][1]:
        p["refused"] = (p.get("refused") or []) + [[p["offer"][0], p["offer"][1]]]
    if st.get("stage") == "ask_today":
        st["stage"] = "offer"
        for x in open_products(st):
            x["refused"] = (x.get("refused") or []) + [[x["due"], today.isoformat()]]
        p = current(st)
        p["entered"] = True
        if len(open_products(st)) > 1:
            # the shared question is over: say so, so that the first offer reads as each product's own first attempt
            return attempt_offer(S, V, st, p, today, ONE_AT_A_TIME)
    return attempt_offer(S, V, st, p, today)


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


def dangling_date(text):
    """Date words that stop where more must follow: 'Tuesday the twenty', 'on the', 'next'."""
    last = (re.findall(r"[a-z]+|\d+", (text or "").lower()) or [""])[-1]
    return last in TENS or last in ("the", "of", "on", "and", "at", "in", "next", "this")


def stage_is(st, name):
    return st.get("stage") == name


def custom_hit(S, V, st, phase):
    name = sval(V, "custom")
    if not name:
        return False
    consume(V, ("custom",))
    c = custom_by_name(S, name)
    if c is None or phase == "custom_cb":
        return False
    verified = bool(st.get("verified"))
    when = c.get("applies_when") or "any"
    if (when == "before_verification" and verified) or (when == "after_verification" and not verified):
        return False
    node = {"presence": "talk_pre", "third_party": "talk_pre", "identity": "talk_id"}.get(phase, "talk_main")
    consume(V, ("presence", "q_kind", "cb_phrase", "id_answer", "id_iso", "id_reply", "reply", "date_phrase", "amount", "applies_to_all"))
    handle_custom(S, V, st, c, node)
    return True


def run(V, S):
    now = parse_now(S, V)
    st = load_state(V)
    if st is None:
        st = {"phase": "presence", "asks": 1, "pending": ""}
        set_final(S, V, st)
        V["farewell"] = phrase(S, "goodbye") or "Goodbye."
        say(V, st, "talk_pre", phrase(S, "opening"), identity_question(S, V))
        save(V, st)
        return
    pend = st.get("pending") or ""
    phase = st.get("phase")
    today = now.date()
    asked = sval(V, "q_kind") if not pend.startswith("tool:") else ""
    st["_cut"] = (not pend.startswith("tool:")) and sval(V, "message_state") == "cut_off"
    consume(V, ("message_state",))
    if not st["_cut"] and not pend.startswith("tool:"):
        st["go_on"] = 0
    answer = answer_for_question(S, asked) if asked in ("ai", "scam") else ""
    if pend == "tool:verify_identity":
        on_verify_result(S, V, st)
    elif pend == "tool:get_account":
        on_account_result(S, V, st, now)
    elif pend == "tool:create_promise":
        on_promise_result(S, V, st, today)
    elif pend == "tool:add_note":
        after_records(S, V, st, today)
    elif pend == "tool:schedule_callback":
        d = tool_result(V, "schedule_callback", st)
        if tool_ok(S, "schedule_callback", d):
            finish(S, V, st, st["situation"] if str(st.get("situation") or "").startswith("custom:") else "callback", phrase(S, "callback_confirm", date=fmt_date(D.fromisoformat(st["cb"][0]), today), time=st["cb"][1]))
        else:
            st["cb_fail"] = int(st.get("cb_fail") or 0) + 1
            if st["cb_fail"] <= 1:
                call_tool(S, V, st, "schedule_callback", {"date": st["cb"][0], "time": st["cb"][1]})
            else:
                finish(S, V, st, "no_callback", phrase(S, "no_callback"))
    elif pend == "tool:transfer_to_agent":
        finish(S, V, st, st.get("situation") or "", phrase(S, "transfer_announce"))
    elif custom_hit(S, V, st, phase):
        pass
    elif phase == "custom_cb":
        on_custom_callback(S, V, st, now)
    elif phase == "presence":
        on_presence(S, V, st, now)
    elif phase == "third_party":
        on_third_party(S, V, st, now)
    elif phase == "identity":
        on_identity_turn(S, V, st)
    elif phase == "main":
        on_main_turn(S, V, st, now)
    else:
        finish(S, V, st, "")
    if st.get("lead") and V.get("next_step") == "bye":
        V["farewell"] = join(st.pop("lead"), V.get("farewell", ""))
    if answer:
        nxt = str(V.get("next_step") or "")
        if nxt.endswith("_fixed"):
            if answer not in (V.get("say_line") or ""):
                say(V, st, nxt[:-len("_fixed")], answer, V.get("say_line") or "")
        elif nxt == "bye":
            if answer not in (V.get("farewell") or ""):
                V["farewell"] = join(answer, V.get("farewell") or "")
        else:
            st["answer_pending"] = answer  # a tool runs first: say it with the next line
    elif st.get("answer_pending") and str(V.get("next_step") or "").endswith("_fixed"):
        say(V, st, V["next_step"][:-len("_fixed")], st.pop("answer_pending"), V.get("say_line") or "")
    st.pop("_cut", None)
    set_final(S, V, st)
    save(V, st)
