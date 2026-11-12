import base64
import io
import zipfile

from kelvo.uploads import extract_text


def make_pdf(text: str) -> bytes:
    """A minimal one-page PDF with real text, built by hand (offsets computed)."""
    stream = f"BT /F1 18 Tf 40 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


def make_docx(paragraphs: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document xmlns:w="x"><w:body>{body}</w:body></w:document>')
    return buf.getvalue()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_extractors():
    kind, text, warn = extract_text("report.pdf", make_pdf("Quarterly revenue was 42 million"))
    assert kind == "pdf" and "Quarterly revenue was 42 million" in text and "[page 1]" in text and warn is None
    kind, text, _ = extract_text("plan.docx", make_docx(["First point", "Second &amp; last"]))
    assert kind == "docx" and text == "First point\nSecond & last"
    assert extract_text("notes.md", "# Hi\nthere".encode())[1] == "# Hi\nthere"
    assert extract_text("photo.png", b"\x89PNG....")[0] == "image"
    assert extract_text("blob.bin", bytes(range(256)))[0] == "binary"


def test_upload_and_chat_with_files(client, tmp_path, monkeypatch):
    from tests.test_app import build, final_messages
    monkeypatch.setenv("KELVO_WORKSPACE", str(tmp_path / "ws"))
    pdf = client.post("/api/uploads", json={"name": "Report Q3.pdf", "data": b64(make_pdf("Revenue grew 12 percent"))}).json()
    doc = client.post("/api/uploads", json={"name": "../../evil/plan.docx", "data": b64(make_docx(["Hire two people"]))}).json()
    assert pdf["kind"] == "pdf" and pdf["chars"] > 0 and doc["name"] == "plan.docx"  # path stripped from the name
    f = client.post("/api/flows", json={"template": "basic-prompting"}).json()
    r = client.post(f"/api/flows/{f['id']}/build", json={"input_value": "Summarize", "session_id": "up", "files": [pdf["id"], doc["id"]]})
    import json as _j
    evs = [_j.loads(l[6:]) for l in r.text.splitlines() if l.startswith("data: ")]
    reply = final_messages(evs)[0]
    assert "Revenue grew 12 percent" in reply and "Hire two people" in reply and "cite file names" in reply
    assert (tmp_path / "ws/uploads/Report Q3.pdf").exists() and (tmp_path / "ws/uploads/plan.docx").exists()
    stored = client.get(f"/api/flows/{f['id']}/messages", params={"session_id": "up"}).json()
    user = stored[0]
    assert user["text"] == "Summarize"  # history keeps your words, not the file contents
    assert [x["name"] for x in user["properties"]["files"]] == ["Report Q3.pdf", "plan.docx"]


def test_upload_errors(client):
    assert client.post("/api/uploads", json={"name": "x.txt", "data": "not base64!!"}).status_code == 422
    big = b64(b"0" * (25 * 1024 * 1024 + 1))
    assert client.post("/api/uploads", json={"name": "x.txt", "data": big}).status_code == 422
    client.post("/api/auth/logout")
    assert client.post("/api/uploads", json={"name": "x.txt", "data": b64(b"hi")}).status_code == 401
