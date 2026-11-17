"""Approval rules for the Command Line tool (Settings → Approvals).

- Allow: commands matching these run without asking (e.g. `git status`, `npm test`).
- Block: commands matching these never run, even with approval switched off.

Patterns are whole commands with * as a wildcard, case-insensitive. A wildcard pattern never
matches a command that chains or redirects (&, |, ;, <, >, backticks, $( ), so `npm test*`
does not allow `npm test && del *`.
"""
from __future__ import annotations

import fnmatch
import re

from . import db

DEFAULT_ALLOW = ["dir", "ls", "pwd", "git status", "git diff", "git log --oneline"]
DEFAULT_BLOCK = ["*rm -rf /", "*rm -rf / *", "*rm -rf ~", "*rm -rf ~/", "*format c:*", "*diskpart*",
                 "*format-volume*", "*clear-disk*", "*rd /s /q c:\\", "*rmdir /s /q c:\\", "*del /s /q c:\\*.*"]
_CHAIN = re.compile(r"[&|;<>`\n\r]|\$\(")
_PROGRAMS_WITH_SUBCOMMANDS = {"git", "npm", "npx", "pnpm", "yarn", "pip", "uv", "uvx", "cargo", "go", "dotnet",
                              "docker", "kubectl", "ollama", "poetry", "conda", "winget", "choco", "gradle", "mvn"}


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def _lines(key: str, default: list[str]) -> list[str]:
    raw = db.get_setting(key)
    if raw is None:
        return list(default)
    return [x.strip() for x in raw.splitlines() if x.strip()]


def allow_list() -> list[str]:
    return _lines("approval_allow", DEFAULT_ALLOW)


def block_list() -> list[str]:
    return _lines("approval_block", DEFAULT_BLOCK)


def save(allow: list[str] | None = None, block: list[str] | None = None) -> None:
    if allow is not None:
        db.set_setting("approval_allow", "\n".join(dict.fromkeys(x.strip() for x in allow if x.strip())))
    if block is not None:
        db.set_setting("approval_block", "\n".join(dict.fromkeys(x.strip() for x in block if x.strip())))


def add_allow(pattern: str) -> None:
    pattern = pattern.strip()
    if pattern and pattern not in allow_list():
        save(allow=allow_list() + [pattern])


def matches(command: str, pattern: str) -> bool:
    cmd, pat = _norm(command), _norm(pattern)
    if not pat:
        return False
    if cmd == pat:
        return True
    if "*" not in pat and "?" not in pat:
        return False
    return not _CHAIN.search(command) and fnmatch.fnmatchcase(cmd, pat)


def allowed(command: str) -> str | None:
    return next((p for p in allow_list() if matches(command, p)), None)


def blocked(command: str) -> str | None:
    cmd = _norm(command)
    return next((p for p in block_list() if fnmatch.fnmatchcase(cmd, _norm(p))), None)


def suggest(command: str) -> str:
    """A sensible 'always allow' pattern: `npm test -- x` → `npm test*`, `python build.py` → `python build.py`."""
    words = command.strip().split()
    if not words or _CHAIN.search(command):
        return command.strip()
    first = re.sub(r"(\.exe|\.cmd|\.bat)$", "", words[0].lower())
    if first in _PROGRAMS_WITH_SUBCOMMANDS and len(words) >= 2:
        return " ".join(words[:2]) + ("*" if len(words) > 2 else "")
    return command.strip()
