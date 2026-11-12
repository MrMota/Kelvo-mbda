"""Files attached in chat: stored, text extracted (PDF, Word, text/code), copied into the workspace.

The agent gets each file's text inline (with its name, so it can cite it). The original is also
copied to <workspace>/uploads/ so the Files tool can read the rest of a long document.
"""
from __future__ import annotations

import base64
import io
import json
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from . import db

MAX_BYTES = 25 * 1024 * 1024
INLINE_TOTAL = 40_000  # characters of attached text given to the model per message
TEXT_EXT = {".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".xml", ".html", ".htm",
            ".log", ".ini", ".cfg", ".toml", ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".cs",
            ".go", ".rs", ".rb", ".php", ".sh", ".ps1", ".bat", ".sql", ".css", ".kt", ".swift", ".r", ".m", ".tex"}


def uploads_dir() -> Path:
    d = Path(db.db_path()).parent / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_name(name: str) -> str:
    name = Path(name.replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .") or "file"
    return name[:120]


def extract_text(name: str, data: bytes) -> tuple[str, str, str | None]:
    """→ (kind, text, warning)."""
    ext = Path(name).suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader

        try:
            reader = PdfReader(io.BytesIO(data))
            pages = [(p.extract_text() or "").strip() for p in reader.pages]
        except Exception as e:  # damaged or encrypted PDFs
            return "pdf", "", f"Couldn't read {name}: {e}"
        text = "\n\n".join(f"[page {i}]\n{t}" for i, t in enumerate(pages, 1) if t)
        warn = None if text.strip() else f"{name} has no text layer (probably a scan), so the agent can't read it."
        return "pdf", text, warn
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
        except Exception as e:
            return "docx", "", f"Couldn't read {name}: {e}"
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab/>", "\t", xml)
        text = re.sub(r"<[^>]+>", "", xml)
        import html as _html

        return "docx", _html.unescape(text).strip(), None
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return "image", "", f"{name} is an image. Kelvo agents read text files for now, so it was saved to the workspace only."
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        if ext in TEXT_EXT:
            return "text", data.decode("latin-1"), None
        return "binary", "", f"{name} isn't a text, PDF or Word file, so it was saved to the workspace only."
    return "text", text, None


def save_upload(name: str, b64: str) -> dict[str, Any]:
    try:
        data = base64.b64decode(b64, validate=True)
    except Exception as e:
        raise ValueError("The file didn't arrive intact; try again.") from e
    if len(data) > MAX_BYTES:
        raise ValueError("Files can be up to 25 MB.")
    name = safe_name(name)
    uid = db.new_id()
    folder = uploads_dir() / uid
    folder.mkdir(parents=True)
    (folder / name).write_bytes(data)
    kind, text, warning = extract_text(name, data)
    (folder / "text.txt").write_text(text, encoding="utf-8")
    meta = {"id": uid, "name": name, "size": len(data), "kind": kind, "chars": len(text), "warning": warning}
    (folder / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def load(uid: str) -> tuple[dict[str, Any], str, Path] | None:
    if not re.fullmatch(r"[0-9a-f-]{36}", uid or ""):
        return None
    folder = uploads_dir() / uid
    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        return meta, (folder / "text.txt").read_text(encoding="utf-8"), folder / meta["name"]
    except (OSError, ValueError, KeyError):
        return None


def attach(file_ids: list[str], workspace: Path | None) -> tuple[list[dict[str, Any]], str]:
    """Copy each file into <workspace>/uploads and build the text block the agent receives."""
    metas, blocks, budget = [], [], INLINE_TOTAL
    for fid in file_ids:
        got = load(str(fid))
        if not got:
            continue
        meta, text, original = got
        rel = None
        if workspace is not None:
            dest_dir = workspace / "uploads"
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / meta["name"]
            if dest.exists() and dest.read_bytes() != original.read_bytes():
                dest = dest_dir / f"{dest.stem}-{meta['id'][:6]}{dest.suffix}"
            shutil.copyfile(original, dest)
            rel = dest.relative_to(workspace).as_posix()
        metas.append({k: meta[k] for k in ("id", "name", "size", "kind")})
        where = f" (saved in the workspace as {rel})" if rel else ""
        if not text.strip():
            blocks.append(f"### {meta['name']}{where}\n[no readable text]")
            continue
        part = text[:budget]
        budget -= len(part)
        cut = ""
        if len(part) < len(text):
            rest = len(text) - len(part)
            cut = (f"\n[… {rest} more characters not shown. The full file is {rel} in the workspace (Files tool).]" if rel
                   else f"\n[… {rest} more characters not shown.]")
        blocks.append(f"### {meta['name']}{where}\n{part}{cut}")
    if not blocks:
        return metas, ""
    return metas, ("\n\nThe user attached these files. Use them to answer and cite file names (and pages for PDFs) "
                   "when you rely on them.\n\n" + "\n\n".join(blocks))
