"""Reading a case's documents: Word and Excel with the standard library (a date cell becomes YYYY-MM-DD), a folder with
sub-folders, the service contract found in the folder. No API call: the files are made here.

    python3 tests/test_documents.py
"""
import json, pathlib, shutil, sys, tempfile, zipfile
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "builder"))
import documents

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
X_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def make_docx(path):
    p = lambda t: f'<w:p><w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:p>'
    cell = lambda t: f"<w:tc>{p(t)}</w:tc>"
    body = (p("Kural 1: Müşteriyi doğrula.") + p("Rule 2: state the debt.")
            + f"<w:tbl><w:tr>{cell('Gün')}{cell('Tatil')}</w:tr><w:tr>{cell('2026-10-29')}{cell('Cumhuriyet Bayramı')}</w:tr></w:tbl>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>')


def make_xlsx(path):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/workbook.xml", f'<workbook xmlns="{X_NS}" xmlns:r="{R_NS}"><sheets><sheet name="Tatiller" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="{X_NS}"><si><t>Tarih</t></si><si><t>Ad</t></si><si><t>Yılbaşı</t></si></sst>')
        z.writestr("xl/styles.xml", f'<styleSheet xmlns="{X_NS}"><numFmts><numFmt numFmtId="164" formatCode="dd.mm.yyyy"/></numFmts>'
                   '<cellXfs><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="14"/></cellXfs></styleSheet>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{X_NS}"><sheetData>'
                   '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
                   '<row r="2"><c r="A2" s="1"><v>46388</v></c><c r="B2" t="s"><v>2</v></c><c r="D2"><v>12.5</v></c></row>'
                   '<row r="3"><c r="A3" s="2"><v>46322</v></c><c r="B3" t="inlineStr"><is><t>Bayram</t></is></c></row>'
                   '</sheetData></worksheet>')


class Trace:
    def __init__(self):
        self.events = []

    def event(self, kind, **data):
        self.events.append(dict(data, event=kind))


def main():
    ok = True

    def check(cond, what):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + what)
        ok = ok and cond

    d = pathlib.Path(tempfile.mkdtemp(prefix="docs-test-"))
    case = d / "case"
    (case / "ekler").mkdir(parents=True)
    make_docx(case / "01-politika.docx")
    make_xlsx(case / "ekler" / "02-tatiller.xlsx")
    (case / "00-mail.md").write_text("Konu: tahsilat\n")
    shutil.copy(ROOT / "tools" / "openapi.json", case / "ekler" / "servis.json")
    (case / "eski.doc").write_bytes(b"\xd0\xcf\x11\xe0")
    (case / ".DS_Store").write_bytes(b"x")

    t = documents.docx_text(case / "01-politika.docx")
    check("Kural 1: Müşteriyi doğrula." in t and "Rule 2: state the debt." in t, "docx: paragraphs in order")
    check("| 2026-10-29 | Cumhuriyet Bayramı |" in t, "docx: a table as rows")
    x = documents.xlsx_text(case / "ekler" / "02-tatiller.xlsx")
    check("## Sheet: Tatiller" in x and "Tarih | Ad" in x, "xlsx: sheet name and shared strings")
    check("2027-01-01 | Yılbaşı |  | 12.5" in x, "xlsx: a custom date format becomes YYYY-MM-DD; empty columns kept; numbers as they are")
    check("2026-10-27 | Bayram" in x, "xlsx: a built-in date format (14) and an inline string")

    tr = Trace()
    docs = documents.read([case], tr)
    names = [n for n, _, _ in docs]
    check(names == ["00-mail.md", "01-politika.docx", "ekler/02-tatiller.xlsx", "ekler/servis.json"], f"a folder with sub-folders, in name order: {names}")
    skipped = next(e for e in tr.events if e["event"] == "documents")["skipped"]
    check([s["file"] for s in skipped] == ["eski.doc"], "an old .doc is named in the trace, a dot file is not read")
    c = documents.contract(docs, tr)
    check(c.name == "servis.json" and any(e["event"] == "contract" for e in tr.events), "the service contract is the folder's OpenAPI JSON")
    shutil.rmtree(d)

    # the reading order: BRIEF first, README second, the others in name order, announcements and Q&A last
    d = pathlib.Path(tempfile.mkdtemp(prefix="docs-order-"))
    for n in ("01-mail.md", "Duyurular.md", "readme.MD", "BRIEF.md", "Sorular ve Cevaplar.md", "02-politika.md", "sorumluluk.md", "akis.svg"):
        (d / n).write_text("<svg><text>Kimlik doğrulama</text></svg>" if n.endswith(".svg") else n)
    names = [n for n, _ in documents.files_of([d])]
    check(names == ["BRIEF.md", "readme.MD", "01-mail.md", "02-politika.md", "akis.svg", "sorumluluk.md", "Duyurular.md", "Sorular ve Cevaplar.md"],
          f"reading order: BRIEF, README, the others by name, announcements and Q&A last: {names}")
    docs = documents.read([d], Trace())
    check(any(n == "akis.svg" and "Kimlik doğrulama" in t for n, t, _ in docs), "an SVG drawing is read as text")
    shutil.rmtree(d)

    print("\nall passed" if ok else "\nSOME FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
