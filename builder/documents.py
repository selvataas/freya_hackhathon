"""A case's documents as text, and its service contract as an OpenAPI document. Nothing here knows a brief.

Markdown and other text files are read as they are; Word (.docx) and Excel (.xlsx) with the standard library (Excel
dates become YYYY-MM-DD); a PDF is given to the model, which writes out its text (cached by the file's hash). The
service contract is the folder's OpenAPI JSON; without one, the model writes it from the contract documents.
"""
import base64, datetime, hashlib, json, pathlib, re, zipfile
import xml.etree.ElementTree as ET

CACHE = pathlib.Path(__file__).resolve().parent.parent / "cache"
TEXT = {".md", ".markdown", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".html", ".htm"}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
X = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


# ---------------------------------------------------------------- Word

def _ptext(p):
    out = []
    for n in p.iter():
        if n.tag == W + "t":
            out.append(n.text or "")
        elif n.tag == W + "tab":
            out.append("\t")
        elif n.tag in (W + "br", W + "cr"):
            out.append("\n")
    return "".join(out)


def docx_text(path):
    """Paragraphs in order; a table as Markdown-like rows."""
    body = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml")).find(W + "body")
    out = []
    for el in list(body if body is not None else []):
        if el.tag == W + "p":
            out.append(_ptext(el))
        elif el.tag == W + "tbl":
            for tr in el.iter(W + "tr"):
                cells = [" ".join(_ptext(p) for p in tc.iter(W + "p")).strip() for tc in tr.findall(W + "tc")]
                out.append("| " + " | ".join(cells) + " |")
            out.append("")
    return "\n".join(out).strip() + "\n"


# ---------------------------------------------------------------- Excel

DATE_FORMAT_IDS = set(range(14, 23)) | {45, 46, 47}


def _date_styles(z, names):
    """Indexes of the cell styles that show a date."""
    if "xl/styles.xml" not in names:
        return set()
    st = ET.fromstring(z.read("xl/styles.xml"))
    custom = {}
    for nf in st.iter(X + "numFmt"):
        code = re.sub(r'"[^"]*"|\[[^\]]*\]|\\.', "", nf.get("formatCode") or "").lower()
        custom[int(nf.get("numFmtId"))] = bool(re.search(r"[dmy]", code)) and "general" not in code
    out = set()
    xfs = st.find(X + "cellXfs")
    for i, xf in enumerate(list(xfs) if xfs is not None else []):
        fid = int(xf.get("numFmtId") or 0)
        if fid in DATE_FORMAT_IDS or custom.get(fid):
            out.add(i)
    return out


def _col(ref):
    n = 0
    for ch in re.match(r"[A-Z]*", ref or "").group(0):
        n = n * 26 + ord(ch) - 64
    return max(n - 1, 0)


def _cell(c, shared, dates):
    t, v = c.get("t"), c.find(X + "v")
    if t == "inlineStr":
        return "".join(x.text or "" for x in c.iter(X + "t"))
    if v is None or v.text is None:
        return ""
    if t == "s":
        return shared[int(v.text)]
    if t == "b":
        return "TRUE" if v.text == "1" else "FALSE"
    if t in ("str", "e"):
        return v.text
    try:
        f = float(v.text)
    except ValueError:
        return v.text
    if int(c.get("s") or 0) in dates:
        d = datetime.datetime(1899, 12, 30) + datetime.timedelta(days=f)
        return d.strftime("%Y-%m-%d") if d.hour == d.minute == 0 else d.strftime("%Y-%m-%d %H:%M")
    return str(int(f)) if f == int(f) else repr(f)


def xlsx_text(path):
    """Every sheet as rows of cells separated by ' | '."""
    z = zipfile.ZipFile(path)
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(X + "si"):
            shared.append("".join(t.text or "" for t in si.iter(X + "t")))
    dates = _date_styles(z, names)
    rels = {}
    if "xl/_rels/workbook.xml.rels" in names:
        for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
            rels[r.get("Id")] = r.get("Target") or ""
    out = []
    for sh in ET.fromstring(z.read("xl/workbook.xml")).iter(X + "sheet"):
        target = rels.get(sh.get(R + "id"), "").lstrip("/")
        part = target if target.startswith("xl/") else "xl/" + target
        if part not in names:
            continue
        out.append(f"## Sheet: {sh.get('name')}")
        for row in ET.fromstring(z.read(part)).iter(X + "row"):
            vals = []
            for c in row.findall(X + "c"):
                col = _col(c.get("r"))
                while len(vals) < col:
                    vals.append("")
                vals.append(_cell(c, shared, dates))
            if any(x.strip() for x in vals):
                out.append(" | ".join(vals))
        out.append("")
    return "\n".join(out).strip() + "\n"


# ---------------------------------------------------------------- PDF, through the model

PDF_SYSTEM = ("You write out the full text of a bank document, word for word, in its own language, in reading order, as "
              "Markdown: headings as headings, lists as lists, tables as Markdown tables. Add nothing, leave nothing out, "
              "translate nothing, comment on nothing.")


def pdf_text(path, trace, allow_llm=True):
    data = pathlib.Path(path).read_bytes()
    key = hashlib.sha256(data).hexdigest()[:16]
    cp = CACHE / f"pdf-{key}.md"
    if cp.exists():
        trace.event("pdf_cache_hit", file=pathlib.Path(path).name, key=key)
        return cp.read_text()
    if not allow_llm:
        raise SystemExit(f"--no-llm: the PDF {pathlib.Path(path).name} has not been read yet (key {key}); nothing was called")
    import extract
    content = [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()}},
               {"type": "text", "text": "Write out the full text of this document."}]
    text = extract._ask(trace, f"read the PDF {pathlib.Path(path).name}", PDF_SYSTEM, [{"role": "user", "content": content}])
    CACHE.mkdir(exist_ok=True)
    cp.write_text(text)
    return text


# ---------------------------------------------------------------- the case

def files_of(paths):
    """(name, path) of every file: a folder is read whole, sub-folders too, in name order."""
    out = []
    for p in paths:
        p = pathlib.Path(p)
        if p.is_dir():
            for f in sorted(x for x in p.rglob("*") if x.is_file()):
                rel = f.relative_to(p)
                if any(part.startswith(".") or part == "__MACOSX" for part in rel.parts):
                    continue
                out.append((rel.as_posix(), f))
        else:
            out.append((p.name, p))
    return out


def read(paths, trace, allow_llm=True):
    """[(name, text, path)] for every document that can be read; the others are named in the trace."""
    docs, skipped = [], []
    for name, f in files_of(paths):
        ext = f.suffix.lower()
        try:
            if ext in TEXT:
                docs.append((name, f.read_text(errors="replace"), f))
            elif ext == ".docx":
                docs.append((name, docx_text(f), f))
            elif ext in (".xlsx", ".xlsm"):
                docs.append((name, xlsx_text(f), f))
            elif ext == ".pdf":
                docs.append((name, pdf_text(f, trace, allow_llm), f))
            else:
                skipped.append({"file": name, "why": "a file type the builder does not read"})
        except SystemExit:
            raise
        except Exception as e:
            skipped.append({"file": name, "why": repr(e)[:200]})
    trace.event("documents", read=[{"file": n, "chars": len(t)} for n, t, _ in docs], skipped=skipped)
    return docs


def is_openapi(path):
    try:
        d = json.loads(pathlib.Path(path).read_text())
    except Exception:
        return False
    return isinstance(d, dict) and isinstance(d.get("paths"), dict) and ("openapi" in d or "swagger" in d)


CONTRACT_SYSTEM = ("You turn a bank's service contract into one OpenAPI 3 JSON document. Keep every operation, its path, method, "
                   "operationId (the service's own name), request fields with their types, allowed values and required flags, and "
                   "the response fields of a success. Invent nothing that the contract does not say. Answer with the JSON only.")
CONTRACT_WORDS = re.compile(r"contract|openapi|swagger|api|service|servis|hizmet|s[oö]zle[sş]me|endpoint", re.I)


def contract(docs, trace, allow_llm=True):
    """The path of the case's OpenAPI JSON. Without one, the model writes it from the documents that describe the
    services (cached by their text)."""
    found = [p for _, _, p in docs if p.suffix.lower() == ".json" and is_openapi(p)]
    if found:
        if len(found) > 1:
            trace.event("warning", message=f"several OpenAPI files; the first is the service contract: {[f.name for f in found]}")
        trace.event("contract", file=found[0].name, how="the case's OpenAPI file")
        return found[0]
    cands = [(n, t) for n, t, p in docs if p.suffix.lower() in (".yaml", ".yml") or CONTRACT_WORDS.search(n) or "openapi" in t[:2000].lower()]
    if not cands:
        raise SystemExit("no service contract found in the case folder: no OpenAPI JSON and no document that names one")
    text = "\n\n".join(f'<document file="{n}">\n{t}\n</document>' for n, t in cands)
    key = hashlib.sha256(text.encode()).hexdigest()[:16]
    cp = CACHE / f"contract-{key}.json"
    if not cp.exists():
        if not allow_llm:
            raise SystemExit(f"--no-llm: the service contract has not been turned into OpenAPI yet (key {key}); nothing was called")
        import extract
        out = extract._ask(trace, "write the service contract as OpenAPI", CONTRACT_SYSTEM, [{"role": "user", "content": text}])
        api = extract._json_from(out)
        if not isinstance(api, dict) or not isinstance(api.get("paths"), dict):
            raise SystemExit("the service contract could not be turned into OpenAPI")
        CACHE.mkdir(exist_ok=True)
        cp.write_text(json.dumps(api, indent=1))
    trace.event("contract", file=cp.name, how="written by the model from the contract documents", sources=[n for n, _ in cands])
    return cp
