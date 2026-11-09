from __future__ import annotations

from typing import Any

from .base import (
    DATA,
    MESSAGE,
    TEXT,
    TEXTLIKE,
    Component,
    Field,
    Message,
    Output,
    fill_prompt,
    prompt_vars,
    to_text,
)


class ChatInput(Component):
    key = "ChatInput"
    display = "Chat Input"
    category = "Input & Output"
    description = "The message typed in the Playground or sent as input_value to the API."
    icon = "message-square"
    tool_mode = False
    fields = [
        Field("input_value", "Default text", "text", "", info="Used when the run has no input."),
        Field("sender_name", "Sender name", "str", "User", advanced=True),
        Field("session_id", "Session ID", "str", "", advanced=True, info="Blank = the run's session."),
        Field("store", "Store in memory", "bool", True, advanced=True),
    ]
    outputs = [Output("message", "Message", MESSAGE)]

    async def out_message(self, ctx) -> Message:
        text = ctx.engine.input_value or await ctx.text("input_value")
        msg = Message(
            text=text,
            sender="user",
            sender_name=await ctx.text("sender_name", "User") or "User",
            session_id=await ctx.text("session_id") or ctx.session_id,
        )
        if await ctx.get("store", True) and text:
            ctx.engine.store_message(msg)
        return msg


class ChatOutput(Component):
    key = "ChatOutput"
    display = "Chat Output"
    category = "Input & Output"
    description = "Shows a reply in the Playground and returns it from the API."
    icon = "message-square-reply"
    tool_mode = False
    fields = [
        Field("input", "Input", "text", accepts=TEXTLIKE, required=True, show_field=False),
        Field("sender_name", "Sender name", "str", "AI", advanced=True),
        Field("store", "Store in memory", "bool", True, advanced=True),
    ]
    outputs = [Output("message", "Message", MESSAGE)]

    async def out_message(self, ctx) -> Message:
        v = await ctx.get("input")
        text = await ctx.text("input")  # raises SkipBranch on inactive branch
        props: dict[str, Any] = dict(v.properties) if isinstance(v, Message) else {}
        props["source"] = props.get("source") or {}
        msg = Message(
            text=text,
            sender="machine",
            sender_name=await ctx.text("sender_name", "AI") or "AI",
            session_id=ctx.session_id,
            properties=props,
        )
        if await ctx.get("store", True):
            ctx.engine.store_message(msg)
        d = msg.to_dict()
        ctx.engine.outputs.append({"component_id": ctx.node_id, "type": "chat", "message": d})
        await ctx.emit("message", {"message": d})
        return msg


class TextInput(Component):
    key = "TextInput"
    display = "Text Input"
    category = "Input & Output"
    description = "A fixed piece of text to feed into other components."
    icon = "type"
    fields = [Field("value", "Text", "text", "", tool_param=True)]
    outputs = [Output("text", "Text", TEXT)]

    async def out_text(self, ctx) -> str:
        return await ctx.text("value")


class TextOutput(Component):
    key = "TextOutput"
    display = "Text Output"
    category = "Input & Output"
    description = "Returns text from the API and shows it in run outputs, without chat memory."
    icon = "file-text"
    tool_mode = False
    fields = [Field("input", "Input", "text", accepts=TEXTLIKE, required=True, show_field=False)]
    outputs = [Output("text", "Text", TEXT)]

    async def out_text(self, ctx) -> str:
        text = await ctx.text("input")
        ctx.engine.outputs.append({"component_id": ctx.node_id, "type": "text", "text": text})
        await ctx.emit("text_output", {"text": text})
        return text


class Prompt(Component):
    key = "Prompt"
    display = "Prompt Template"
    category = "Prompts"
    description = "Write a prompt with {variables}; each variable becomes an input port."
    icon = "braces"
    fields = [
        Field(
            "template",
            "Template",
            "text",
            "Answer the user's question.\n\nQuestion: {question}",
            info="Use {name} for a variable. Write {{ and }} for literal braces.",
        )
    ]
    outputs = [Output("prompt", "Prompt", MESSAGE)]

    def dynamic_fields(self, params: dict[str, Any]) -> list[Field]:
        tpl = params.get("template", self.fields[0].default)
        return [Field(v, v, "text", "", accepts=TEXTLIKE, tool_param=True) for v in prompt_vars(tpl)]

    async def out_prompt(self, ctx) -> Message:
        tpl = await ctx.text("template")
        values = {v: await ctx.text(v) for v in prompt_vars(tpl)}
        return Message(text=fill_prompt(tpl, values), sender="user", sender_name="Prompt")


__all__ = ["ChatInput", "ChatOutput", "TextInput", "TextOutput", "Prompt", "DATA"]
