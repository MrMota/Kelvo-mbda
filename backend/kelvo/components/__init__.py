"""Component registry. Order here is the order in the editor sidebar."""
from __future__ import annotations

from .agent import Agent, Skill
from .base import Component
from .io import ChatInput, ChatOutput, Prompt, TextInput, TextOutput
from .logic import IfElse, KnowledgeBase, MessageHistory, Parser, SplitText
from .models import OllamaEmbeddings, OllamaModel, StructuredOutput
from .power import Files, Shell, WebSearch
from .tools import Calculator, CurrentDate, RunFlow, URLFetch

ALL: list[type[Component]] = [
    ChatInput, ChatOutput, TextInput, TextOutput,
    Prompt,
    OllamaModel, OllamaEmbeddings, StructuredOutput,
    Agent, Skill,
    WebSearch, URLFetch, Files, Shell, Calculator, CurrentDate, RunFlow,
    MessageHistory,
    KnowledgeBase,
    Parser, SplitText,
    IfElse,
]
REGISTRY: dict[str, type[Component]] = {c.key: c for c in ALL}
CATEGORIES = ["Input & Output", "Prompts", "Models", "Agents", "Tools", "Memory", "Vector Stores", "Processing", "Logic"]


def specs() -> dict:
    return {"categories": CATEGORIES, "components": [c.spec() for c in ALL]}
