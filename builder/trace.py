"""The run trace: one JSON object per line. Secrets are masked before anything is written."""
import json, os, re, time

SECRET_ENV = ("FREYA_API_KEY", "FREYA_BANK_TEAM_KEY", "ANTHROPIC_API_KEY", "OPENROUTER_API_KEY")
PATTERNS = [re.compile(r"fak_[A-Za-z0-9_\-]{6,}"), re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}"), re.compile(r"sk-or-[A-Za-z0-9_\-]{6,}"),
            re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{10,}")]


def mask(text):
    for k in SECRET_ENV:
        v = os.environ.get(k)
        if v and len(v) >= 6:
            text = text.replace(v, "***" + k + "***")
    for p in PATTERNS:
        text = p.sub("***", text)
    return text


class Trace:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.f = open(path, "a")
        self.t0 = time.time()

    def event(self, kind, **data):
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "elapsed_s": round(time.time() - self.t0, 1), "event": kind, **data}
        self.f.write(mask(json.dumps(rec, default=str, ensure_ascii=False)) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()
