"""Component model: fields, outputs, data types and the runtime values that flow on edges."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, ClassVar

if TYPE_CHECKING:  # pragma: no cover
    from ..engine import NodeCtx

# Data types that travel on edges. The frontend colours ports by these.
MESSAGE = "Message"
TEXT = "Text"
DATA = "Data"
LLM = "LanguageModel"
EMBEDDINGS = "Embeddings"
TOOL = "Tool"
SKILL = "Skill"

TEXTLIKE = [MESSAGE, TEXT, DATA]


class Stop:
    """Sentinel for an inactive branch (If-Else). Downstream nodes skip."""

    def __repr__(self) -> str:
        return "STOP"


STOP = Stop()


@dataclass
class Message:
    text: str
    sender: str = "machine"  # user | machine
    sender_name: str = "AI"
    session_id: str = ""
    properties: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LLMConfig:
    base_url: str
    model: str
    options: dict[str, Any] = field(default_factory=dict)
    keep_alive: str | None = None


@dataclass
class EmbeddingsConfig:
    base_url: str
    model: str


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[[dict[str, Any]], Awaitable[str]]

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


@dataclass
class SkillDef:
    name: str
    description: str
    body: str


@dataclass
class Field:
    name: str
    display: str
    type: str = "str"  # str | text | int | float | bool | select | model | embed_model | secret | json | skills | flow | skill
    default: Any = None
    accepts: list[str] | None = None  # if set, the field has an input port
    list: bool = False  # accepts many connections
    required: bool = False
    advanced: bool = False
    tool_param: bool = False  # filled by the agent when the node is a tool
    options: list[str] | None = None
    info: str = ""
    placeholder: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    show_field: bool = True  # False → port only, no inline editor

    def spec(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Output:
    name: str
    display: str
    type: str


class Component:
    key: ClassVar[str]
    display: ClassVar[str]
    category: ClassVar[str]
    description: ClassVar[str] = ""
    icon: ClassVar[str] = "box"
    fields: ClassVar[list[Field]] = []
    outputs: ClassVar[list[Output]] = []
    tool_mode: ClassVar[bool] = True  # can be switched into tool mode
    tool_default: ClassVar[bool] = False  # starts in tool mode when dropped
    tool_output: ClassVar[str | None] = None  # which output a tool call returns

    def dynamic_fields(self, params: dict[str, Any]) -> list[Field]:
        return []

    def all_fields(self, params: dict[str, Any]) -> list[Field]:
        return list(self.fields) + self.dynamic_fields(params)

    async def compute(self, ctx: "NodeCtx", output: str) -> Any:
        fn = getattr(self, f"out_{output}", None)
        if fn is None:
            raise ValueError(f"{self.display} has no output '{output}'")
        return await fn(ctx)

    @classmethod
    def spec(cls) -> dict[str, Any]:
        return {
            "key": cls.key,
            "display": cls.display,
            "category": cls.category,
            "description": cls.description,
            "icon": cls.icon,
            "fields": [f.spec() for f in cls.fields],
            "outputs": [asdict(o) for o in cls.outputs],
            "tool_mode": cls.tool_mode,
            "tool_default": cls.tool_default,
            "dynamic": cls.dynamic_fields is not Component.dynamic_fields,
        }


# ---------------------------------------------------------------- helpers

def to_text(v: Any) -> str:
    if v is None or isinstance(v, Stop):
        return ""
    if isinstance(v, Message):
        return v.text
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "\n\n".join(to_text(x) for x in v)
    if isinstance(v, dict):
        if set(v.keys()) == {"text"} or ("text" in v and isinstance(v["text"], str) and len(v) <= 2):
            return v["text"]
        return json.dumps(v, ensure_ascii=False, indent=2)
    return str(v)


def to_message(v: Any, **kw: Any) -> Message:
    if isinstance(v, Message):
        return v
    return Message(text=to_text(v), **kw)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_") or "tool"


PROMPT_VAR = re.compile(r"(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})")


def prompt_vars(template: str) -> list[str]:
    seen: list[str] = []
    for m in PROMPT_VAR.finditer(template or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def fill_prompt(template: str, values: dict[str, str]) -> str:
    out = PROMPT_VAR.sub(lambda m: values.get(m.group(1), m.group(0)), template or "")
    return out.replace("{{", "{").replace("}}", "}")
