#!/usr/bin/env python3
"""Generate synthetic .docx test fixtures with tracked changes + comments.
No real data. Lets you exercise the whole pipeline offline.

    python3 src/make_fixtures.py tests/fixtures
"""
import os, sys, zipfile

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

def docx(path, body, comments=""):
    doc = f'<?xml version="1.0"?><w:document {W}><w:body>{body}</w:body></w:document>'
    z = zipfile.ZipFile(path, "w")
    z.writestr("[Content_Types].xml", "<Types/>")
    z.writestr("word/document.xml", doc)
    if comments:
        z.writestr("word/comments.xml", f'<?xml version="1.0"?><w:comments {W}>{comments}</w:comments>')
    z.close()

def para(text): return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'

def redline(before, delw, insw, author):
    return (f'<w:p><w:r><w:t xml:space="preserve">{before} </w:t></w:r>'
            f'<w:del w:id="1" w:author="{author}"><w:r><w:delText>{delw}</w:delText></w:r></w:del>'
            f'<w:ins w:id="2" w:author="{author}"><w:r><w:t>{insw}</w:t></w:r></w:ins></w:p>')

def commented(cid, text, author, ctext):
    p = (f'<w:p><w:commentRangeStart w:id="{cid}"/>'
         f'<w:r><w:t>{text}</w:t></w:r>'
         f'<w:commentRangeEnd w:id="{cid}"/><w:r><w:commentReference w:id="{cid}"/></w:r></w:p>')
    c = f'<w:comment w:id="{cid}" w:author="{author}"><w:p><w:r><w:t>{ctext}</w:t></w:r></w:p></w:comment>'
    return p, c

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures"
    os.makedirs(out, exist_ok=True)
    # deal 1: MSA, internal reviewer edits liability
    p, c = commented(1, "Limitation of Liability clause", "Jane Doe",
                     "cap should be on fees, not uncapped")
    docx(os.path.join(out, "Acme MSA - review v2.docx"),
         para("Master Service Agreement") +
         redline("Total liability", "shall be unlimited", "shall not exceed 100% of fees", "Jane Doe") +
         p, c)
    # deal 2: NDA, external counsel edit + internal comment
    p, c = commented(2, "Confidentiality term is five years", "John Smith",
                     "reduce to 3 years per standard")
    docx(os.path.join(out, "Beta NDA - counterparty markup.docx"),
         para("Non-Disclosure Agreement") +
         redline("The term is", "five (5) years", "three (3) years", "External Counsel LLP") +
         p, c)
    print(f"fixtures written to {out}/")

if __name__ == "__main__":
    main()
